# tests/unit/ingestion/test_unified_cli.py
"""Tests for unified ingestion CLI (src/ingestion/unified/cli.py)."""

import argparse
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.ingestion.unified.commands import cmd_run
from src.ingestion.unified.flow import IngestionResult


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


class TestArgParsing:
    """Verify CLI arg parsing for each subcommand."""

    def _parse(self, *argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Unified Ingestion Pipeline (v3.2.1)",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("-v", "--verbose", action="store_true")
        subparsers = parser.add_subparsers(dest="command", required=True)

        run_p = subparsers.add_parser("run")
        run_p.add_argument("--watch", "-w", action="store_true")

        subparsers.add_parser("preflight")
        bootstrap_p = subparsers.add_parser("bootstrap")
        bootstrap_p.add_argument("--require-colbert", action="store_true")

        schema_check_p = subparsers.add_parser("schema-check")
        schema_check_p.add_argument("--require-colbert", action="store_true")

        return parser.parse_args(list(argv))

    def test_run_default(self):
        args = self._parse("run")
        assert args.command == "run"
        assert args.watch is False

    def test_run_watch_short(self):
        args = self._parse("run", "-w")
        assert args.watch is True

    def test_run_watch_long(self):
        args = self._parse("run", "--watch")
        assert args.watch is True

    def test_preflight(self):
        args = self._parse("preflight")
        assert args.command == "preflight"

    def test_bootstrap(self):
        args = self._parse("bootstrap")
        assert args.command == "bootstrap"
        assert args.require_colbert is False

    def test_bootstrap_require_colbert(self):
        args = self._parse("bootstrap", "--require-colbert")
        assert args.command == "bootstrap"
        assert args.require_colbert is True

    def test_schema_check(self):
        args = self._parse("schema-check")
        assert args.command == "schema-check"
        assert args.require_colbert is False

    def test_schema_check_require_colbert(self):
        args = self._parse("schema-check", "--require-colbert")
        assert args.command == "schema-check"
        assert args.require_colbert is True

    def test_verbose_flag(self):
        args = self._parse("-v", "run")
        assert args.verbose is True

    def test_no_command_raises(self):
        with pytest.raises(SystemExit):
            self._parse()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Verify logging configuration."""

    def test_default_level_info(self):
        from src.ingestion.unified.main import setup_logging

        root = logging.getLogger()
        prev_level = root.level
        prev_handlers = list(root.handlers)
        try:
            # Reset handlers so basicConfig can set the level
            root.handlers.clear()
            setup_logging(verbose=False)
            assert root.level == logging.INFO
        finally:
            root.handlers.clear()
            root.handlers.extend(prev_handlers)
            root.setLevel(prev_level)

    def test_verbose_level_debug(self):
        from src.ingestion.unified.main import setup_logging

        root = logging.getLogger()
        prev_level = root.level
        prev_handlers = list(root.handlers)
        try:
            root.handlers.clear()
            setup_logging(verbose=True)
            assert root.level == logging.DEBUG
        finally:
            root.handlers.clear()
            root.handlers.extend(prev_handlers)
            root.setLevel(prev_level)

    def test_noisy_loggers_quieted(self):
        from src.ingestion.unified.main import setup_logging

        root = logging.getLogger()
        httpx_logger = logging.getLogger("httpx")
        httpcore_logger = logging.getLogger("httpcore")
        prev_level = root.level
        prev_handlers = list(root.handlers)
        prev_httpx = httpx_logger.level
        prev_httpcore = httpcore_logger.level
        try:
            root.handlers.clear()
            setup_logging()
            assert httpx_logger.level == logging.WARNING
            assert httpcore_logger.level == logging.WARNING
        finally:
            root.handlers.clear()
            root.handlers.extend(prev_handlers)
            root.setLevel(prev_level)
            httpx_logger.setLevel(prev_httpx)
            httpcore_logger.setLevel(prev_httpcore)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_response(json_data=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = json_data or {}
    return resp


def _fail_response(status=500):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = {}
    return resp


def _make_config(**overrides):
    """Create a MagicMock config with sensible defaults."""
    config = MagicMock()
    config.qdrant_url = overrides.get("qdrant_url", "http://qdrant:6333")
    config.collection_name = overrides.get("collection_name", "test_col")
    config.bge_m3_url = overrides.get("bge_m3_url", "http://bge:8000")
    config.database_url = overrides.get("database_url", "postgresql://test@localhost/db")
    config.sync_dir = overrides.get("sync_dir", Path("/tmp/sync"))
    config.supported_extensions = overrides.get("supported_extensions", frozenset({".md"}))
    return config


# ---------------------------------------------------------------------------
# cmd_preflight
# ---------------------------------------------------------------------------


class TestCmdPreflight:
    """Test preflight dependency checks."""

    @pytest.fixture
    def args(self):
        return argparse.Namespace(command="preflight", verbose=False)

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_all_checks_pass(self, args, capsys, tmp_path):
        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response({"result": {"points_count": 42}})
        mock_client.post.return_value = _ok_response()

        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / "knowledge.md").write_text("# test", encoding="utf-8")

        config = _make_config(sync_dir=sync_dir)
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            result = await cmd_preflight(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "READY" in output
        assert "[OK]" in output

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_qdrant_fail_returns_1(self, args, capsys):
        mock_client = AsyncMock()
        mock_client.get.side_effect = [_fail_response(404)]  # qdrant collection
        mock_client.post.return_value = _ok_response()

        config = _make_config()
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            result = await cmd_preflight(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "NOT READY" in output

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_connection_error_handled(self, args, capsys):
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")
        mock_client.post.side_effect = httpx.ConnectError("refused")

        config = _make_config()
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            result = await cmd_preflight(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "[FAIL]" in output

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
            "RAG_TESTING": "true",
            "LANGFUSE_TRACING_ENABLED": "false",
            "OTEL_SDK_DISABLED": "true",
        },
        clear=True,
    )
    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
        },
        clear=True,
    )
    async def test_preflight_has_no_converter_check(self, args, capsys, tmp_path):
        """Markdown-only ingestion (#3235): preflight never probes a converter."""
        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response({"result": {"points_count": 42}})
        mock_client.post.return_value = _ok_response()

        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / "knowledge.md").write_text("# test", encoding="utf-8")

        config = _make_config(sync_dir=sync_dir)

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            result = await cmd_preflight(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "Docling" not in output
        assert "docling" not in output

    async def test_missing_env_vars_warned(self, args, capsys):
        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response({"result": {"points_count": 0}})
        mock_client.post.return_value = _ok_response()

        config = _make_config()
        env = {
            "RAG_TESTING": "true",
            "LANGFUSE_TRACING_ENABLED": "false",
            "OTEL_SDK_DISABLED": "true",
        }
        with (
            patch.dict("os.environ", env, clear=True),
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            await cmd_preflight(args)

        output = capsys.readouterr().out
        assert "[WARN]" in output
        assert "Missing env vars" in output

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_sync_dir_missing_fails(self, args, capsys, tmp_path):
        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response({"result": {"points_count": 0}})
        mock_client.post.return_value = _ok_response()

        config = _make_config(sync_dir=tmp_path / "missing-sync")
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("httpx.AsyncClient") as MockClient,
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value = mock_client
            mock_ctx.__aexit__.return_value = False
            MockClient.return_value = mock_ctx

            from src.ingestion.unified.cli import cmd_preflight

            result = await cmd_preflight(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "Sync dir" in output
        assert "[FAIL]" in output


# ---------------------------------------------------------------------------
# cmd_preflight — Qdrant authentication (#3494)
# ---------------------------------------------------------------------------

QDRANT_AUTH_HOST = "qdrant-preflight.test"
BGE_AUTH_HOST = "bge-preflight.test"


class TestPreflightQdrantAuth:
    """Request-level Qdrant authentication for cmd_preflight (#3494).

    Uses httpx.MockTransport so assertions run against real request objects
    (per-host headers) and real response statuses. The Qdrant key must be
    scoped to the Qdrant request only — the same client probes BGE-M3.
    """

    @staticmethod
    def _base_env(tmp_path: Path) -> dict[str, str]:
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / "knowledge.md").write_text("# test", encoding="utf-8")
        return {
            "QDRANT_URL": f"http://{QDRANT_AUTH_HOST}:6333",
            "BGE_M3_URL": f"http://{BGE_AUTH_HOST}:8000",
            "COLLECTION_NAME": "preflight_col",
            "SYNC_DIR": str(sync_dir),
            "RAG_TESTING": "true",
            "LANGFUSE_TRACING_ENABLED": "false",
            "LANGFUSE_ENABLED": "false",
            "OTEL_SDK_DISABLED": "true",
        }

    @staticmethod
    def _patch_async_client(transport: httpx.MockTransport):
        """Make httpx.AsyncClient(...) construct a real client on ``transport``."""
        real_async_client = httpx.AsyncClient

        def _factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_async_client(*args, **kwargs)

        return patch("httpx.AsyncClient", side_effect=_factory)

    async def _run_preflight(
        self, env: dict[str, str], qdrant_responder
    ) -> tuple[int, list[httpx.Request]]:
        """Run cmd_preflight with the real UnifiedConfig from ``env``.

        Records every outgoing request. Qdrant requests go to
        ``qdrant_responder``; BGE probes always answer 200 without auth.
        """
        requests_seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            if request.url.host == QDRANT_AUTH_HOST:
                return qdrant_responder(request)
            return httpx.Response(200, json={"embeddings": [[0.1]]})

        transport = httpx.MockTransport(handler)
        args = argparse.Namespace(command="preflight", verbose=False)
        with (
            patch.dict(os.environ, env, clear=True),
            self._patch_async_client(transport),
        ):
            from src.ingestion.unified.cli import cmd_preflight

            exit_code = await cmd_preflight(args)
        return exit_code, requests_seen

    def _qdrant_requests(self, requests_seen: list[httpx.Request]) -> list[httpx.Request]:
        return [r for r in requests_seen if r.url.host == QDRANT_AUTH_HOST]

    def _bge_requests(self, requests_seen: list[httpx.Request]) -> list[httpx.Request]:
        return [r for r in requests_seen if r.url.host == BGE_AUTH_HOST]

    async def test_configured_key_authenticates_protected_qdrant(self, tmp_path, capsys):
        """A correctly configured key makes preflight of a protected collection pass."""
        KEY = "correct-preflight-key"

        def respond(request: httpx.Request) -> httpx.Response:
            if request.headers.get("api-key") == KEY:
                return httpx.Response(200, json={"result": {"points_count": 7}})
            return httpx.Response(401, json={"status": {"error": "Unauthorized"}})

        env = self._base_env(tmp_path) | {"QDRANT_API_KEY": KEY}
        exit_code, requests_seen = await self._run_preflight(env, respond)

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "READY" in output
        assert KEY not in output  # credential never surfaces in output

        qdrant_requests = self._qdrant_requests(requests_seen)
        assert len(qdrant_requests) == 1
        request = qdrant_requests[0]
        assert request.method == "GET"
        assert request.url.path == "/collections/preflight_col"
        assert request.headers.get("api-key") == KEY

    async def test_wrong_key_against_protected_qdrant_is_not_ready(self, tmp_path, capsys):
        """A wrong key keeps a controlled failed result (HTTP 401, exit 1)."""

        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"status": {"error": "Unauthorized"}})

        env = self._base_env(tmp_path) | {"QDRANT_API_KEY": "wrong-preflight-key"}
        exit_code, requests_seen = await self._run_preflight(env, respond)

        assert exit_code == 1
        output = capsys.readouterr().out
        assert "NOT READY" in output
        assert "HTTP 401" in output
        assert "wrong-preflight-key" not in output
        # The configured (wrong) key was still sent to Qdrant only.
        assert self._qdrant_requests(requests_seen)[0].headers.get("api-key") == (
            "wrong-preflight-key"
        )

    async def test_missing_key_against_protected_qdrant_is_not_ready(self, tmp_path, capsys):
        """No configured key against a protected collection: controlled 401, exit 1."""

        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"status": {"error": "Unauthorized"}})

        env = self._base_env(tmp_path)  # QDRANT_API_KEY absent
        exit_code, requests_seen = await self._run_preflight(env, respond)

        assert exit_code == 1
        output = capsys.readouterr().out
        assert "NOT READY" in output
        assert "HTTP 401" in output
        assert "api-key" not in self._qdrant_requests(requests_seen)[0].headers

    async def test_empty_key_unauthenticated_qdrant_sends_no_auth(self, tmp_path, capsys):
        """Empty key against an open Qdrant: no auth header sent, preflight passes."""

        def respond(request: httpx.Request) -> httpx.Response:
            assert "api-key" not in request.headers
            assert "authorization" not in request.headers
            return httpx.Response(200, json={"result": {"points_count": 3}})

        env = self._base_env(tmp_path) | {"QDRANT_API_KEY": ""}
        exit_code, _ = await self._run_preflight(env, respond)

        assert exit_code == 0
        assert "READY" in capsys.readouterr().out

    async def test_bge_probes_never_receive_qdrant_credentials(self, tmp_path):
        """The Qdrant key must never leak to the BGE host via shared client headers."""

        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"result": {"points_count": 7}})

        env = self._base_env(tmp_path) | {"QDRANT_API_KEY": "correct-preflight-key"}
        exit_code, requests_seen = await self._run_preflight(env, respond)

        assert exit_code == 0
        bge_requests = self._bge_requests(requests_seen)
        assert {r.url.path for r in bge_requests} == {"/encode/dense", "/encode/sparse"}
        for request in bge_requests:
            assert "api-key" not in request.headers
            assert "authorization" not in request.headers


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------


class TestCmdRun:
    """Test run command dispatch."""

    def test_run_once_called(self):
        config = _make_config()
        mock_run_once = MagicMock()
        mock_run_once.return_value = IngestionResult()

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("src.ingestion.unified.flow.run_once", mock_run_once),
        ):
            from src.ingestion.unified.cli import cmd_run

            args = argparse.Namespace(command="run", watch=False, verbose=False)
            result = cmd_run(args)

        assert result == 0
        mock_run_once.assert_called_once_with(config)

    def test_run_watch_called(self):
        config = _make_config()
        mock_run_watch = MagicMock()

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("src.ingestion.unified.flow.run_watch", mock_run_watch),
        ):
            from src.ingestion.unified.cli import cmd_run

            args = argparse.Namespace(command="run", watch=True, verbose=False)
            result = cmd_run(args)

        assert result == 0
        mock_run_watch.assert_called_once_with(config)

    # -------------------------------------------------------------------
    # One-shot exit-code contract (#3489)
    # -------------------------------------------------------------------

    @staticmethod
    def _run_one_shot(run_once_return) -> int:
        """Invoke the real cmd_run in one-shot mode with a scripted run_once."""
        config = _make_config()
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("src.ingestion.unified.flow.run_once", return_value=run_once_return),
        ):
            return cmd_run(argparse.Namespace(watch=False))

    def test_partial_failure_exits_1(self):
        """A finished one-shot with per-file errors must fail the command (#3489)."""
        result = IngestionResult(processed=2, skipped=1, errors=1, error_details=["broken.md"])

        assert self._run_one_shot(result) == 1

    def test_successful_run_exits_0(self):
        result = IngestionResult(processed=2, skipped=0, errors=0)

        assert self._run_one_shot(result) == 0

    def test_bare_result_exits_0(self):
        assert self._run_one_shot(IngestionResult()) == 0

    def test_noop_only_skipped_exits_0(self):
        result = IngestionResult(processed=0, skipped=3, errors=0)

        assert self._run_one_shot(result) == 0

    def test_run_once_exception_reraises(self):
        """Unexpected exceptions are re-raised, not swallowed into an exit code."""
        config = _make_config()
        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.flow.run_once",
                MagicMock(side_effect=RuntimeError("boom")),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            cmd_run(argparse.Namespace(watch=False))

    def test_watch_mode_calls_only_run_watch_and_exits_0(self):
        config = _make_config()
        mock_run_watch = MagicMock()
        mock_run_once = MagicMock()

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("src.ingestion.unified.flow.run_watch", mock_run_watch),
            patch("src.ingestion.unified.flow.run_once", mock_run_once),
        ):
            exit_code = cmd_run(argparse.Namespace(watch=True))

        assert exit_code == 0
        mock_run_watch.assert_called_once_with(config)
        mock_run_once.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_bootstrap
# ---------------------------------------------------------------------------


class TestResolveQuantizationConfig:
    """Unit tests for _resolve_quantization_config() helper."""

    def test_binary_returns_binary_quantization(self):
        from qdrant_client.models import BinaryQuantization

        from src.ingestion.unified.commands import _resolve_quantization_config

        result = _resolve_quantization_config("binary")
        assert isinstance(result, BinaryQuantization)
        assert result.binary.always_ram is True

    def test_scalar_returns_scalar_quantization(self):
        from qdrant_client.models import ScalarQuantization, ScalarType

        from src.ingestion.unified.commands import _resolve_quantization_config

        result = _resolve_quantization_config("scalar")
        assert isinstance(result, ScalarQuantization)
        assert result.scalar.type == ScalarType.INT8
        assert result.scalar.quantile == 0.99
        assert result.scalar.always_ram is True

    def test_off_returns_none(self):
        from src.ingestion.unified.commands import _resolve_quantization_config

        assert _resolve_quantization_config("off") is None

    def test_default_is_binary(self):
        from qdrant_client.models import BinaryQuantization

        from src.ingestion.unified.commands import _resolve_quantization_config

        # No argument → default "binary"
        result = _resolve_quantization_config()
        assert isinstance(result, BinaryQuantization)

    def test_invalid_raises_value_error(self):
        from src.ingestion.unified.commands import _resolve_quantization_config

        with pytest.raises(ValueError, match="QDRANT_QUANTIZATION_MODE"):
            _resolve_quantization_config("unknown")


class TestCmdBootstrap:
    """Test bootstrap command."""

    @pytest.fixture
    def args(self):
        return argparse.Namespace(command="bootstrap", verbose=False, require_colbert=False)

    async def test_collection_already_exists(self, args, capsys):
        config = _make_config(collection_name="existing_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.return_value = MagicMock()  # exists

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "already exists" in output
        client.create_collection.assert_not_called()

    async def test_collection_exists_require_colbert_fails_on_drift(self, capsys):
        config = _make_config(collection_name="existing_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        collection_info = MagicMock()
        collection_info.config.params.vectors = {"dense": MagicMock()}
        collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        client.get_collection.return_value = collection_info

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(
                argparse.Namespace(command="bootstrap", verbose=False, require_colbert=True)
            )

        assert result == 1
        output = capsys.readouterr().out
        assert "schema drift" in output.lower()
        assert "colbert" in output

    async def test_connection_failure(self, args, capsys):
        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.side_effect = ConnectionError("refused")

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "[FAIL]" in output

    async def test_creates_collection_when_missing(self, args, capsys):
        from qdrant_client.http.exceptions import UnexpectedResponse

        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.side_effect = UnexpectedResponse(
            status_code=404, reason_phrase="Not found", content=b"", headers={}
        )

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        client.create_collection.assert_called_once()
        output = capsys.readouterr().out
        assert "Bootstrap completed" in output

    async def test_creates_canonical_payload_indexes_and_strict_mode(self, args):
        """Bootstrap consumes the canonical index map and applies strict mode (#3333)."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        from src.runtime.qdrant.contracts import (
            KNOWLEDGE_PAYLOAD_INDEXES,
            flat_payload_indexes,
            strict_mode_config,
        )

        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.side_effect = UnexpectedResponse(
            status_code=404, reason_phrase="Not found", content=b"", headers={}
        )

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        created: dict[str, str] = {}
        for call in client.create_payload_index.call_args_list:
            created[call.kwargs["field_name"]] = call.kwargs["field_schema"].value
        assert created == dict(flat_payload_indexes(KNOWLEDGE_PAYLOAD_INDEXES))

        # Strict mode is owned by explicit bootstrap, never by read paths (#3333).
        client.update_collection.assert_called_once_with(
            collection_name="new_col",
            strict_mode_config=strict_mode_config(),
        )

    async def test_existing_collection_is_not_repatched(self, args):
        """Existing collections are not mutated by an idempotent bootstrap run."""
        config = _make_config(collection_name="existing_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.return_value = MagicMock()  # exists

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        client.update_collection.assert_not_called()
        client.create_payload_index.assert_not_called()

    @patch.dict("os.environ", {"QDRANT_QUANTIZATION_MODE": "scalar"})
    async def test_bootstrap_scalar_quantization(self, args, capsys):
        from qdrant_client.http.exceptions import UnexpectedResponse
        from qdrant_client.models import ScalarQuantization

        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.side_effect = UnexpectedResponse(
            status_code=404, reason_phrase="Not found", content=b"", headers={}
        )

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        call_kwargs = client.create_collection.call_args.kwargs
        dense_params = call_kwargs["vectors_config"]["dense"]
        assert isinstance(dense_params.quantization_config, ScalarQuantization)

    @patch.dict("os.environ", {"QDRANT_QUANTIZATION_MODE": "off"})
    async def test_bootstrap_no_quantization(self, args, capsys):
        from qdrant_client.http.exceptions import UnexpectedResponse

        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.side_effect = UnexpectedResponse(
            status_code=404, reason_phrase="Not found", content=b"", headers={}
        )

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 0
        call_kwargs = client.create_collection.call_args.kwargs
        dense_params = call_kwargs["vectors_config"]["dense"]
        assert dense_params.quantization_config is None

    @patch.dict("os.environ", {"QDRANT_QUANTIZATION_MODE": "bad_value"})
    async def test_bootstrap_invalid_mode_returns_1(self, args, capsys):
        from qdrant_client.http.exceptions import UnexpectedResponse

        config = _make_config(collection_name="new_col")
        client = MagicMock()
        client.get_collections.return_value = MagicMock()
        client.get_collection.side_effect = UnexpectedResponse(
            status_code=404, reason_phrase="Not found", content=b"", headers={}
        )

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_bootstrap

            result = await cmd_bootstrap(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "[FAIL]" in output or "QDRANT_QUANTIZATION_MODE" in output


class TestCmdSchemaCheck:
    """Test schema-check command."""

    async def test_schema_check_passes_when_requirements_met(self, capsys):
        config = _make_config(collection_name="existing_col")
        client = MagicMock()
        collection_info = MagicMock()
        collection_info.config.params.vectors = {"dense": MagicMock(), "colbert": MagicMock()}
        collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        client.get_collection.return_value = collection_info

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_schema_check

            result = await cmd_schema_check(
                argparse.Namespace(command="schema-check", verbose=False, require_colbert=True)
            )

        assert result == 0
        output = capsys.readouterr().out
        assert "Schema valid" in output

    async def test_schema_check_fails_when_colbert_missing(self, capsys):
        config = _make_config(collection_name="existing_col")
        client = MagicMock()
        collection_info = MagicMock()
        collection_info.config.params.vectors = {"dense": MagicMock()}
        collection_info.config.params.sparse_vectors = {"bm42": MagicMock()}
        client.get_collection.return_value = collection_info

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch("qdrant_client.QdrantClient", return_value=client),
        ):
            from src.ingestion.unified.cli import cmd_schema_check

            result = await cmd_schema_check(
                argparse.Namespace(command="schema-check", verbose=False, require_colbert=True)
            )

        assert result == 1
        output = capsys.readouterr().out
        assert "Schema drift" in output
        assert "colbert" in output


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMainDispatch:
    """Test main() routes commands correctly."""

    @patch("src.ingestion.unified.main.cmd_run", return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_run(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "run"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_called_once()

    @patch("src.ingestion.unified.main.cmd_preflight", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_preflight(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "preflight"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.main.cmd_bootstrap", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_bootstrap(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "bootstrap"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.main.cmd_schema_check", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_schema_check(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "schema-check", "--require-colbert"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.main.cmd_coverage_check", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_coverage_check(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "coverage-check"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.main.cmd_backfill_colbert", return_value=0)
    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_dispatches_backfill_colbert(
        self, mock_dotenv, mock_logging, mock_cmd, monkeypatch
    ):
        monkeypatch.setattr("sys.argv", ["cli", "backfill-colbert", "--dry-run"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_called_once()
        called_args = mock_cmd.call_args.args[0]
        assert called_args.dry_run is True

    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_calls_load_dotenv(self, mock_dotenv, mock_logging, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "run"])

        from src.ingestion.unified.cli import main

        with patch("src.ingestion.unified.main.cmd_run", return_value=0):
            main()

        mock_dotenv.assert_called_once()

    @patch("src.ingestion.unified.main.setup_logging")
    @patch("src.ingestion.unified.main.load_dotenv")
    def test_main_verbose_flag_passed(self, mock_dotenv, mock_logging, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "-v", "run"])

        from src.ingestion.unified.cli import main

        with patch("src.ingestion.unified.main.cmd_run", return_value=0):
            main()

        mock_logging.assert_called_once_with(True)
