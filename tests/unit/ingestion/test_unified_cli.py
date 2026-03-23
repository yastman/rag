# tests/unit/ingestion/test_unified_cli.py
"""Tests for unified ingestion CLI (src/ingestion/unified/cli.py)."""

import argparse
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras


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

        subparsers.add_parser("status")
        subparsers.add_parser("preflight")
        bootstrap_p = subparsers.add_parser("bootstrap")
        bootstrap_p.add_argument("--require-colbert", action="store_true")

        schema_check_p = subparsers.add_parser("schema-check")
        schema_check_p.add_argument("--require-colbert", action="store_true")

        reprocess_p = subparsers.add_parser("reprocess")
        reprocess_p.add_argument("--file-id")
        reprocess_p.add_argument("--errors", action="store_true")

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

    def test_status(self):
        args = self._parse("status")
        assert args.command == "status"

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

    def test_reprocess_file_id(self):
        args = self._parse("reprocess", "--file-id", "abc123")
        assert args.command == "reprocess"
        assert args.file_id == "abc123"
        assert args.errors is False

    def test_reprocess_errors(self):
        args = self._parse("reprocess", "--errors")
        assert args.errors is True
        assert args.file_id is None

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
        from src.ingestion.unified.cli import setup_logging

        root = logging.getLogger()
        # Reset handlers so basicConfig can set the level
        root.handlers.clear()
        setup_logging(verbose=False)
        assert root.level == logging.INFO

    def test_verbose_level_debug(self):
        from src.ingestion.unified.cli import setup_logging

        root = logging.getLogger()
        root.handlers.clear()
        setup_logging(verbose=True)
        assert root.level == logging.DEBUG

    def test_noisy_loggers_quieted(self):
        from src.ingestion.unified.cli import setup_logging

        setup_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("cocoindex").level == logging.INFO


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
    config.docling_url = overrides.get("docling_url", "http://docling:5001")
    config.database_url = overrides.get("database_url", "postgresql://test@localhost/db")
    config.sync_dir = overrides.get("sync_dir", Path("/tmp/sync"))
    config.supported_extensions = overrides.get(
        "supported_extensions",
        frozenset(
            {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".md", ".txt", ".html", ".htm", ".csv"}
        ),
    )
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
            "DOCLING_URL": "http://docling:5001",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_all_checks_pass(self, args, capsys):
        mock_client = AsyncMock()
        mock_client.get.return_value = _ok_response({"result": {"points_count": 42}})
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

        assert result == 0
        output = capsys.readouterr().out
        assert "READY" in output
        assert "[OK]" in output

    @patch.dict(
        "os.environ",
        {
            "QDRANT_URL": "http://qdrant:6333",
            "BGE_M3_URL": "http://bge:8000",
            "DOCLING_URL": "http://docling:5001",
            "INGESTION_DATABASE_URL": "postgresql://test@localhost/db",
        },
    )
    async def test_qdrant_fail_returns_1(self, args, capsys):
        mock_client = AsyncMock()
        mock_client.get.side_effect = [
            _fail_response(404),  # qdrant collection
            _ok_response(),  # docling health
        ]
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
            "DOCLING_URL": "http://docling:5001",
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
            "DOCLING_URL": "http://docling:5001",
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
# cmd_status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    """Test status command output."""

    @pytest.fixture
    def args(self):
        return argparse.Namespace(command="status", verbose=False)

    async def test_status_output_format(self, args, capsys):
        config = _make_config(collection_name="test_col")

        manager = AsyncMock()
        manager.get_stats.return_value = {"indexed": 10, "pending": 5, "error": 2}
        manager.get_dlq_count.return_value = 1

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_status

            result = await cmd_status(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "Ingestion Status" in output
        assert "indexed: 10" in output
        assert "TOTAL: 17" in output
        assert "DLQ: 1" in output
        assert "test_col" in output

    async def test_status_empty_stats(self, args, capsys):
        config = _make_config(collection_name="empty_col")

        manager = AsyncMock()
        manager.get_stats.return_value = {}
        manager.get_dlq_count.return_value = 0

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_status

            result = await cmd_status(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "TOTAL: 0" in output

    async def test_status_closes_manager(self, args):
        config = _make_config()

        manager = AsyncMock()
        manager.get_stats.return_value = {"indexed": 1}
        manager.get_dlq_count.return_value = 0

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_status

            await cmd_status(args)

        manager.close.assert_awaited_once()

    async def test_status_reports_supported_file_count(self, args, capsys, tmp_path):
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / "one.pdf").write_text("pdf")
        (sync_dir / "two.docx").write_text("docx")
        (sync_dir / "ignored.tmp").write_text("tmp")

        config = _make_config(collection_name="test_col", sync_dir=sync_dir)
        manager = AsyncMock()
        manager.get_stats.return_value = {"indexed": 2}
        manager.get_dlq_count.return_value = 0

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_status

            result = await cmd_status(args)

        assert result == 0
        output = capsys.readouterr().out
        assert "Sync dir:" in output
        assert "Supported files: 2" in output


# ---------------------------------------------------------------------------
# cmd_run
# ---------------------------------------------------------------------------


class TestCmdRun:
    """Test run command dispatch."""

    def test_run_once_called(self):
        config = _make_config()
        mock_run_once = MagicMock()

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


# ---------------------------------------------------------------------------
# cmd_reprocess
# ---------------------------------------------------------------------------


class TestCmdReprocess:
    """Test reprocess command."""

    async def test_reprocess_file_id(self):
        config = _make_config()
        pool = AsyncMock()
        manager = AsyncMock()
        manager._get_pool.return_value = pool

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_reprocess

            args = argparse.Namespace(
                command="reprocess", file_id="abc123", errors=False, verbose=False
            )
            result = await cmd_reprocess(args)

        assert result == 0
        pool.execute.assert_awaited_once()
        sql_call = pool.execute.call_args
        assert "abc123" in sql_call.args

    async def test_reprocess_errors(self):
        config = _make_config()
        pool = AsyncMock()
        pool.execute.return_value = "UPDATE 5"
        manager = AsyncMock()
        manager._get_pool.return_value = pool

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_reprocess

            args = argparse.Namespace(command="reprocess", file_id=None, errors=True, verbose=False)
            result = await cmd_reprocess(args)

        assert result == 0
        sql_call = pool.execute.call_args
        assert "error" in sql_call.args[0]

    async def test_reprocess_no_args_returns_1(self, capsys):
        config = _make_config()
        manager = AsyncMock()
        manager._get_pool.return_value = AsyncMock()

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_reprocess

            args = argparse.Namespace(
                command="reprocess", file_id=None, errors=False, verbose=False
            )
            result = await cmd_reprocess(args)

        assert result == 1
        output = capsys.readouterr().out
        assert "Specify --file-id or --errors" in output

    async def test_reprocess_closes_manager(self):
        config = _make_config()
        manager = AsyncMock()
        manager._get_pool.return_value = AsyncMock()

        with (
            patch("src.ingestion.unified.config.UnifiedConfig", return_value=config),
            patch(
                "src.ingestion.unified.state_manager.UnifiedStateManager",
                return_value=manager,
            ),
        ):
            from src.ingestion.unified.cli import cmd_reprocess

            args = argparse.Namespace(command="reprocess", file_id="x", errors=False, verbose=False)
            await cmd_reprocess(args)

        manager.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# cmd_bootstrap
# ---------------------------------------------------------------------------


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

    @patch("src.ingestion.unified.cli.cmd_run", return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_run(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "run"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_called_once()

    @patch("src.ingestion.unified.cli.cmd_status", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_status(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "status"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.cli.cmd_preflight", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_preflight(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "preflight"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.cli.cmd_bootstrap", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_bootstrap(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "bootstrap"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.cli.cmd_reprocess", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_reprocess(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "reprocess", "--errors"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.cli.cmd_schema_check", new_callable=AsyncMock, return_value=0)
    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_dispatches_schema_check(self, mock_dotenv, mock_logging, mock_cmd, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "schema-check", "--require-colbert"])

        from src.ingestion.unified.cli import main

        result = main()
        assert result == 0
        mock_cmd.assert_awaited_once()

    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_calls_load_dotenv(self, mock_dotenv, mock_logging, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "run"])

        from src.ingestion.unified.cli import main

        with patch("src.ingestion.unified.cli.cmd_run", return_value=0):
            main()

        mock_dotenv.assert_called_once()

    @patch("src.ingestion.unified.cli.setup_logging")
    @patch("src.ingestion.unified.cli.load_dotenv")
    def test_main_verbose_flag_passed(self, mock_dotenv, mock_logging, monkeypatch):
        monkeypatch.setattr("sys.argv", ["cli", "-v", "run"])

        from src.ingestion.unified.cli import main

        with patch("src.ingestion.unified.cli.cmd_run", return_value=0):
            main()

        mock_logging.assert_called_once_with(True)
