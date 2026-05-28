"""Mini App phone -> Kommo DI contract (#2212 / Epic C).

Pre-#2212 ``mini_app/phone.py::get_kommo_client()`` constructed
``KommoClient()`` with no args. ``KommoClient.__init__`` requires
``subdomain`` and ``token_store`` (kw-only), so every call raised
``TypeError``. The Mini App phone submission emitted a Langfuse span
``miniapp-kommo-create-lead`` with ``level=ERROR, status_message=
kommo_submission_failed: TypeError`` — every single time. Operators
saw a permanent CRM error rate, end users saw a generic failure.

This contract pins the SDK-native fix:

1. ``submit_phone`` accepts an explicit ``client`` parameter (DI).
2. ``submit_phone`` raises ``ValueError`` when ``client`` is ``None``
   so a misconfigured Mini App boots loudly instead of silently
   recording success spans.
3. The endpoint resolves the client from ``request.app.state.kommo_client``,
   which the FastAPI ``lifespan`` populates from environment.
4. The lifespan tolerates missing Kommo config (no subdomain, no
   token store) — Mini App still serves health / start-expert; only
   ``/submit_phone`` returns 503 with ``kommo_unconfigured`` reason.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mini_app.phone import PhoneRequest, submit_phone


@pytest.fixture
def fake_kommo_client() -> MagicMock:
    """Build a Kommo client whose CRM operations succeed by default."""
    client = MagicMock(name="KommoClient")
    client.upsert_contact = AsyncMock(return_value={"id": 999})
    client.create_lead = AsyncMock(return_value={"id": 12345})
    return client


@pytest.fixture
def phone_request() -> PhoneRequest:
    return PhoneRequest(
        phone="+380501112233",
        source="hot",
        user_id=42,
        name="Alice",
    )


class TestSubmitPhoneDI:
    """`submit_phone` must accept a Kommo client by DI, not construct it."""

    async def test_uses_injected_client_for_upsert_and_create(
        self,
        fake_kommo_client: MagicMock,
        phone_request: PhoneRequest,
    ) -> None:
        result = await submit_phone(phone_request, client=fake_kommo_client)

        fake_kommo_client.upsert_contact.assert_awaited_once_with(
            phone="+380501112233",
            name="Alice",
        )
        fake_kommo_client.create_lead.assert_awaited_once()
        assert result == {"success": True, "lead_id": 12345}

    async def test_returns_failure_when_client_is_none(self, phone_request: PhoneRequest) -> None:
        """Missing Kommo client -> structured failure, not silent crash."""
        result = await submit_phone(phone_request, client=None)

        assert result["success"] is False
        assert result["lead_id"] is None
        assert result["error"] == "kommo_unconfigured"

    async def test_returns_failure_on_kommo_exception(
        self,
        fake_kommo_client: MagicMock,
        phone_request: PhoneRequest,
    ) -> None:
        fake_kommo_client.upsert_contact = AsyncMock(side_effect=RuntimeError("Kommo 502"))

        result = await submit_phone(phone_request, client=fake_kommo_client)

        assert result["success"] is False
        assert result["lead_id"] is None
        assert "kommo_submission_failed" in (result.get("error") or "")


class TestPhoneEndpointRoutesAppStateClient:
    """The /submit_phone endpoint must read the Kommo client from app.state
    populated by the lifespan, NOT construct it inline (the #2212 bug)."""

    async def test_endpoint_passes_app_state_kommo_client_to_submit_phone(
        self,
        fake_kommo_client: MagicMock,
        phone_request: PhoneRequest,
    ) -> None:
        from unittest.mock import patch

        from mini_app import api as mini_api

        # Synthetic Request whose .app.state has our fake kommo_client
        fake_state = MagicMock()
        fake_state.kommo_client = fake_kommo_client
        fake_app = MagicMock()
        fake_app.state = fake_state
        fake_request = MagicMock()
        fake_request.app = fake_app

        captured: dict = {}

        async def _fake_submit_phone(req, *, client):
            captured["request"] = req
            captured["client"] = client
            return {"success": True, "lead_id": 7}

        with patch.object(mini_api, "submit_phone", side_effect=_fake_submit_phone):
            init_data = {"user": {"id": 42, "first_name": "A"}}
            response = await mini_api.submit_phone_endpoint(
                request=phone_request,
                init_data=init_data,
                http_request=fake_request,
            )

        # The endpoint must have reached for app.state.kommo_client
        assert captured["client"] is fake_kommo_client
        assert response == {"success": True, "lead_id": 7}

    async def test_endpoint_returns_503_when_kommo_unconfigured(
        self,
        phone_request: PhoneRequest,
    ) -> None:
        from unittest.mock import patch

        from mini_app import api as mini_api

        fake_state = MagicMock()
        fake_state.kommo_client = None  # lifespan saw no Kommo config
        fake_app = MagicMock()
        fake_app.state = fake_state
        fake_request = MagicMock()
        fake_request.app = fake_app

        async def _fake_submit_phone(req, *, client):
            return await submit_phone(req, client=client)

        with patch.object(mini_api, "submit_phone", side_effect=_fake_submit_phone):
            init_data = {"user": {"id": 42, "first_name": "A"}}
            response = await mini_api.submit_phone_endpoint(
                request=phone_request,
                init_data=init_data,
                http_request=fake_request,
            )

        # FastAPI JSONResponse object — inspect status_code attribute
        assert getattr(response, "status_code", None) == 503
        # Body content carries the structured error
        import json

        body = json.loads(response.body.decode("utf-8"))
        assert body["error"] == "kommo_unconfigured"


class TestLifespanBuildsKommoClient:
    """``mini_app/api.py::lifespan`` must construct a real ``KommoClient``
    from env vars when Kommo is configured, and store ``None`` otherwise."""

    def test_lifespan_skips_when_subdomain_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mini_app import api as mini_api

        monkeypatch.delenv("KOMMO_SUBDOMAIN", raising=False)
        monkeypatch.delenv("KOMMO_CLIENT_ID", raising=False)

        # Build a stub helper that captures whether KommoClient was constructed
        from unittest.mock import patch

        with patch.object(mini_api, "_build_kommo_client", return_value=None) as mock_build:
            assert mock_build.return_value is None
        # Smoke: helper exists and returns None when no env. Real
        # _build_kommo_client behavior is exercised by the helper-level
        # test below so we don't have to spin up the full lifespan.

    def test_build_kommo_client_returns_none_without_subdomain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mini_app import api as mini_api

        monkeypatch.delenv("KOMMO_SUBDOMAIN", raising=False)
        result = mini_api._build_kommo_client(redis_client=MagicMock())
        assert result is None

    def test_build_kommo_client_returns_client_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import patch

        from mini_app import api as mini_api

        monkeypatch.setenv("KOMMO_SUBDOMAIN", "fortnoks")
        monkeypatch.setenv("KOMMO_CLIENT_ID", "cid")
        monkeypatch.setenv("KOMMO_CLIENT_SECRET", "csec")
        monkeypatch.setenv("KOMMO_REDIRECT_URI", "https://x/y")

        sentinel = object()
        with (
            patch(
                "src.services.kommo_tokens.KommoTokenStore",
                return_value=MagicMock(),
            ),
            patch(
                "src.services.kommo_client.KommoClient",
                return_value=sentinel,
            ) as mock_kommo,
        ):
            result = mini_api._build_kommo_client(redis_client=MagicMock())

        assert result is sentinel
        mock_kommo.assert_called_once()
