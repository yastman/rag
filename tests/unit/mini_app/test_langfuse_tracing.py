"""Mini App Langfuse trace coverage (#1658).

Regression locks: every Mini App entry point that hits the bot/CRM funnel
must emit a named, propagated, PII-safe Langfuse trace. Before #1658 the
Mini App had zero trace coverage — leads created via Mini App and the
Kommo upsert/create-lead pair were invisible in Langfuse, and the funnel
`Mini App -> /start q_<expert> -> Telegram dialog -> CRM` could not be
reconstructed in Langfuse Sessions UI.

Contract enforced here:

1. `mini_app.api.start_expert`, `mini_app.api.phone`, and
   `mini_app.phone.submit_phone` are wrapped with `@observe` and reach
   `propagate_attributes(session_id=f"miniapp-{user_id}", user_id=...)`.
2. PII (phone, name, raw deeplink UUID, full message) is NOT captured —
   `capture_input=False, capture_output=False` and curated payloads omit
   the sensitive keys.
3. CRM upsert/create-lead failures inside `submit_phone` raise the
   surrounding span to `level="ERROR"` with a bounded `status_message`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("fastapi")

from httpx import ASGITransport, AsyncClient

import mini_app.api as api_mod
import mini_app.phone as phone_mod
from mini_app.api import app
from mini_app.phone import PhoneRequest, submit_phone


# ---------------------------------------------------------------------------
# Helper: a fixture that records `propagate_attributes(...)` invocations
# without breaking the surrounding `@observe`-decorated function.
# ---------------------------------------------------------------------------


def _make_propagate_recorder() -> tuple[MagicMock, MagicMock]:
    """Return (mock_cm, mock_factory).

    `mock_factory` records every kwargs it was called with and returns the
    context manager `mock_cm`, which is a no-op `with`-statement target.
    """
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=None)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    return mock_cm, mock_factory


# ---------------------------------------------------------------------------
# 1. @observe decorators are applied — static lock so a future revert can't
#    silently drop tracing.
# ---------------------------------------------------------------------------


class TestMiniAppObserveCoverage:
    """`@observe` must wrap every Mini App entry point on the funnel path."""

    def test_start_expert_handler_is_observed(self):
        # `@observe` (or its langfuse-disabled stub) wraps the coroutine and
        # leaves `__wrapped__` accessible. We accept either marker, mirroring
        # tests/unit/services/test_voyage_observability.py.
        fn = api_mod.start_expert
        assert hasattr(fn, "__wrapped__") or hasattr(fn, "_langfuse_observation"), (
            "mini_app.api.start_expert must be wrapped with @observe (#1658)."
        )

    def test_phone_handler_is_observed(self):
        fn = api_mod.phone
        assert hasattr(fn, "__wrapped__") or hasattr(fn, "_langfuse_observation"), (
            "mini_app.api.phone must be wrapped with @observe (#1658)."
        )

    def test_submit_phone_is_observed(self):
        fn = phone_mod.submit_phone
        assert hasattr(fn, "__wrapped__") or hasattr(fn, "_langfuse_observation"), (
            "mini_app.phone.submit_phone must be wrapped with @observe (#1658)."
        )

    def test_observability_symbols_imported_in_api(self):
        """`mini_app.api` must import `observe` and `propagate_attributes`.

        Without these the `@observe` static lock above can be bypassed by
        re-defining a local `observe` shim. Make the import explicit.
        """
        import mini_app.api as mod

        assert hasattr(mod, "observe"), "mini_app.api must import `observe` (#1658)"
        assert hasattr(mod, "propagate_attributes"), (
            "mini_app.api must import `propagate_attributes` (#1658)"
        )

    def test_observability_symbols_imported_in_phone(self):
        import mini_app.phone as mod

        assert hasattr(mod, "observe"), "mini_app.phone must import `observe` (#1658)"
        assert hasattr(mod, "get_client"), (
            "mini_app.phone must import `get_client` for ERROR-level span updates (#1658)"
        )


# ---------------------------------------------------------------------------
# 2. `propagate_attributes` is called with the funnel-grouping session_id
#    `miniapp-{user_id}` and SDK-shaped tags / user_id.
# ---------------------------------------------------------------------------


class TestPropagateAttributesContract:
    """Funnel must be reconstructable in Langfuse Sessions UI (#1658)."""

    @pytest.mark.asyncio
    async def test_start_expert_propagates_session_user_tags(self):
        """`/api/start-expert` propagates session_id=miniapp-{user_id} + user_id + tags."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.publish = AsyncMock()

        async def _override_redis():
            return mock_redis

        # FastAPI dependency override avoids the real Redis connection.
        app.dependency_overrides[api_mod.get_redis] = _override_redis
        # Override auth — user_id=42 matches the session_id assertion below.
        app.dependency_overrides[api_mod.get_validated_init_data] = lambda: {
            "user": {"id": 42, "first_name": "Test"},
            "auth_date": "0",
        }

        _, mock_propagate = _make_propagate_recorder()

        try:
            with (
                patch.object(api_mod, "propagate_attributes", mock_propagate),
                patch.dict("os.environ", {"BOT_USERNAME": "testbot"}, clear=False),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/start-expert",
                        json={
                            "expert_id": "consultant",
                            "message": "ignored-secret-content",
                            "query_id": "q-1",
                        },
                    )
            # Body of the endpoint succeeded, so propagate_attributes was reached.
            assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.pop(api_mod.get_redis, None)
            app.dependency_overrides.pop(api_mod.get_validated_init_data, None)

        assert mock_propagate.call_count >= 1, (
            "start_expert must enter `propagate_attributes(...)` exactly once."
        )
        kwargs = mock_propagate.call_args.kwargs
        assert kwargs.get("session_id") == "miniapp-42", (
            "session_id must be `miniapp-{user_id}` so the Mini App and the "
            "subsequent Telegram /start q_<expert> trace group together."
        )
        assert kwargs.get("user_id") == "42"
        tags = kwargs.get("tags") or []
        assert "miniapp" in tags
        assert "start-expert" in tags
        assert "consultant" in tags, "expert_id must appear as a tag for funnel filtering"

    @pytest.mark.asyncio
    async def test_phone_propagates_session_user_tags(self):
        mock_kommo = MagicMock()
        mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
        mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

        # Override auth — user_id=7 matches the session_id assertion below.
        app.dependency_overrides[api_mod.get_validated_init_data] = lambda: {
            "user": {"id": 7, "first_name": "Test"},
            "auth_date": "0",
        }

        _, mock_propagate = _make_propagate_recorder()

        try:
            with (
                patch.object(api_mod, "propagate_attributes", mock_propagate),
                patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/phone",
                        json={
                            "phone": "+359888123456",
                            "source": "viewing_consultant",
                            "user_id": 7,
                        },
                    )
        finally:
            app.dependency_overrides.pop(api_mod.get_validated_init_data, None)

        assert resp.status_code == 200, resp.text
        assert mock_propagate.call_count >= 1
        kwargs = mock_propagate.call_args.kwargs
        assert kwargs.get("session_id") == "miniapp-7"
        assert kwargs.get("user_id") == "7"
        tags = kwargs.get("tags") or []
        assert "miniapp" in tags
        assert "submit-phone" in tags
        assert "viewing_consultant" in tags, "source must appear as a tag for funnel filtering"


# ---------------------------------------------------------------------------
# 3. Kommo failure inside submit_phone must surface as a Langfuse ERROR span.
# ---------------------------------------------------------------------------


class TestKommoFailureSpan:
    """CRM outages must be visible in Langfuse, not just as logs (#1658)."""

    @pytest.mark.asyncio
    async def test_kommo_failure_marks_span_error(self):
        mock_lf = MagicMock()
        mock_lf.update_current_span = MagicMock()

        with (
            patch("mini_app.phone.get_client", return_value=mock_lf),
            patch("mini_app.phone.get_kommo_client", side_effect=Exception("CRM down")),
        ):
            await submit_phone(
                PhoneRequest(phone="+359888123456", source="viewing_consultant", user_id=99)
            )

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, (
            "submit_phone must call `update_current_span(level='ERROR', ...)` on Kommo "
            "failure so the funnel break is visible in Langfuse, not only in logs."
        )
        msg = error_calls[0].get("status_message") or ""
        assert isinstance(msg, str)
        assert msg, "status_message must be set"
        assert len(msg) <= 200, (
            "status_message must be bounded (<=200 chars) to avoid payload bloat in Langfuse."
        )

    @pytest.mark.asyncio
    async def test_kommo_success_does_not_emit_error_span(self):
        mock_kommo = MagicMock()
        mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
        mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

        mock_lf = MagicMock()
        mock_lf.update_current_span = MagicMock()

        with (
            patch("mini_app.phone.get_client", return_value=mock_lf),
            patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        ):
            await submit_phone(
                PhoneRequest(phone="+359888123456", source="viewing_consultant", user_id=99)
            )

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert not error_calls, "Kommo success must not emit ERROR-level span"

    @pytest.mark.asyncio
    async def test_no_phone_or_name_in_curated_output(self):
        """Curated `update_current_span(output=...)` MUST NOT contain PII (#1658)."""
        mock_kommo = MagicMock()
        mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
        mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

        mock_lf = MagicMock()
        mock_lf.update_current_span = MagicMock()

        with (
            patch("mini_app.phone.get_client", return_value=mock_lf),
            patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        ):
            await submit_phone(
                PhoneRequest(
                    phone="+359888123456",
                    name="Иван",
                    source="viewing_consultant",
                    user_id=99,
                )
            )

        for call in mock_lf.update_current_span.call_args_list:
            payload = call.kwargs.get("output") or {}
            serialized = repr(payload)
            assert "+359888123456" not in serialized, (
                "Curated output must NOT include the raw phone number"
            )
            assert "Иван" not in serialized, (
                "Curated output must NOT include the user-provided name"
            )


# ---------------------------------------------------------------------------
# 4. Sanity: capture_input/output flags on @observe are False everywhere on
#    the Mini App funnel path. AST-based check works whether or not Langfuse
#    is installed in the test env, so the contract cannot drift silently.
# ---------------------------------------------------------------------------


class TestObserveCaptureFlags:
    """`@observe(..., capture_input=False, capture_output=False)` per #1658."""

    @staticmethod
    def _observe_decorator_kwargs(module_path: str, func_name: str) -> dict[str, str]:
        """Return the keyword arguments of the `@observe(...)` decorator.

        Source-level inspection so the contract is enforced even when the
        Langfuse SDK is absent and `@observe` is the no-op stub.
        """
        import ast
        from pathlib import Path

        source = Path(module_path).read_text(encoding="utf-8")
        tree = ast.parse(source)

        target: ast.AsyncFunctionDef | ast.FunctionDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == func_name:
                target = node
                break

        assert target is not None, f"{func_name} not found in {module_path}"

        for dec in target.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if isinstance(func, ast.Name) and func.id == "observe":
                return {kw.arg: ast.unparse(kw.value) for kw in dec.keywords if kw.arg}
            if isinstance(func, ast.Attribute) and func.attr == "observe":
                return {kw.arg: ast.unparse(kw.value) for kw in dec.keywords if kw.arg}

        raise AssertionError(f"{func_name} has no @observe(...) decorator in {module_path}")

    @pytest.mark.parametrize(
        ("module", "func_name"),
        [
            ("mini_app/api.py", "start_expert"),
            ("mini_app/api.py", "phone"),
            ("mini_app/phone.py", "submit_phone"),
        ],
    )
    def test_observe_does_not_capture_payloads(self, module: str, func_name: str) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        kwargs = self._observe_decorator_kwargs(str(repo_root / module), func_name)
        assert kwargs.get("capture_input") == "False", (
            f"{module}::{func_name} must use `@observe(..., capture_input=False)` (#1658). "
            f"Found: {kwargs}"
        )
        assert kwargs.get("capture_output") == "False", (
            f"{module}::{func_name} must use `@observe(..., capture_output=False)` (#1658). "
            f"Found: {kwargs}"
        )
        assert "name" in kwargs and kwargs["name"].startswith("'miniapp-"), (
            f"{module}::{func_name} must use a `miniapp-*` span name (#1658). Found: {kwargs}"
        )
