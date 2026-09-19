"""Promotion cannot turn absent or skipped evidence into success."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.e2e import full_stack_gate as gate


@pytest.mark.parametrize("run_id", ["", "dev", "../other", "ABCDEF123456", "a" * 13])
def test_rejects_foreign_project_names(run_id):
    with pytest.raises(ValueError):
        gate.project_name(run_id)


@pytest.mark.parametrize(
    "body",
    [
        "",
        "<testcase><skipped/></testcase>",
        "<testcase><failure/></testcase>",
        "<testcase><error/></testcase>",
    ],
)
def test_required_report_rejects_missing_success(tmp_path, body):
    report = tmp_path / "junit.xml"
    report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    with pytest.raises(ValueError):
        gate.strict_result(report)


def test_counts_actual_completed_cases(tmp_path):
    report = tmp_path / "junit.xml"
    report.write_text("<testsuites><testsuite><testcase/><testcase/></testsuite></testsuites>")
    assert gate.strict_result(report) == 2


def test_drops_ambient_credentials_and_selection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing")
    monkeypatch.setenv("REDIS_URL", "redis://foreign-host")
    assert not {"OPENAI_API_KEY", "PYTEST_ADDOPTS", "REDIS_URL"} & gate.clean_environment().keys()


@pytest.mark.parametrize("fault", ["missing", "unhealthy", "restarted", "foreign"])
def test_snapshot_requires_six_owned_healthy_services(monkeypatch, fault):
    rows = [
        {
            "project": "rag-e2e-012345abcdef",
            "service": name,
            "status": "running",
            "health": "healthy",
            "restarts": 0,
        }
        for name in gate.SERVICES
    ]
    if fault == "missing":
        rows.pop()
    else:
        key, value = {
            "unhealthy": ("health", "unhealthy"),
            "restarted": ("restarts", 1),
            "foreign": ("project", "dev"),
        }[fault]
        rows[0][key] = value
    monkeypatch.setattr(
        gate,
        "command",
        lambda args, _env: (
            "id1 id2" if "ps" in args else "\n".join(json.dumps(row) for row in rows)
        ),
    )
    with pytest.raises(ValueError):
        gate.service_snapshot(["docker", "compose"], "rag-e2e-012345abcdef", {})


@pytest.mark.parametrize("failure", [None, "build", "bootstrap", "skip", "test"])
def test_full_command_keeps_failure_and_exact_cleanup_evidence(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "resources", lambda *_: {})
    monkeypatch.setattr(
        gate, "service_snapshot", lambda *_a, **_k: [{"service": "bot", "healthy": True}]
    )
    calls = []
    run_dir = tmp_path / "logs/e2e-full/012345abcdef"
    existing_state = tmp_path / ".apartments_ingestion_state_apartments.json"
    existing_state.write_text("existing operator state")

    def command(args, _env, **_kwargs):
        calls.append(args)
        if "scripts.demo_bootstrap" in args:
            from argparse import Namespace

            from scripts.demo_bootstrap import _state_path

            assert _kwargs["cwd"] == run_dir
            assert _env["PYTHONPATH"] == str(tmp_path)
            assert _env["PYTHON_DOTENV_DISABLED"] == "1"
            assert _env["QDRANT_COLLECTION"] == "e2e_012345abcdef_documents"
            for flag in ("--qdrant-url", "--bge-url"):
                assert args[args.index(flag) + 1] == "http://127.0.0.1:12345"
            assert (
                Path(args[args.index("--apartments-csv") + 1]) == tmp_path / "data/apartments.csv"
            )
            assert Path(args[args.index("--knowledge-corpus") + 1]) == tmp_path / "data/test"
            state = run_dir / _state_path(Namespace(apartments_collection="apartments"))
            state.write_text("run-owned bootstrap state")
            if failure == "bootstrap":
                raise RuntimeError("bootstrap failed")
            return "both product collections ready"
        if "rev-parse" in args:
            return "frozen-sha"
        if "--services" in args:
            return "\n".join(gate.SERVICES)
        if "--build" in args and failure == "build":
            raise RuntimeError("build failed")
        if "port" in args:
            return "127.0.0.1:12345"
        return ""

    def pytest_run(args, **kwargs):
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert kwargs["env"]["E2E_HARNESS_REQUIRED"] == "1"
        report = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--junitxml="))
        Path(report).write_text(
            "<testsuite><testcase>"
            + ("<skipped/>" if failure == "skip" else "")
            + "</testcase></testsuite>"
        )
        return subprocess.CompletedProcess(args, 1 if failure == "test" else 0)

    monkeypatch.setattr(gate, "command", command)
    monkeypatch.setattr(gate.subprocess, "run", pytest_run)
    result = gate.main(["--model-dir", str(tmp_path), "--run-id", "012345abcdef"])
    assert result == (0 if failure is None else 1)
    evidence = json.loads((tmp_path / "logs/e2e-full/012345abcdef/result.json").read_text())
    assert evidence["cleaned"] is True
    assert evidence["passed"] is (failure is None)
    down = next(call for call in calls if "down" in call)
    assert down[2:4] == ["-p", "rag-e2e-012345abcdef"]
    assert "--volumes" in down
    assert existing_state.read_text() == "existing operator state"
    starts = [call for call in calls if "up" in call]
    assert set(starts[0][-4:]) == {"postgres", "redis", "qdrant", "bge-m3"}
    if failure in {"build", "bootstrap"}:
        assert len(starts) == 1
        assert evidence["suites"] == []
    else:
        assert len(starts) == 2
        assert set(starts[1][-2:]) == {"bot", "ingestion"}
        bootstrap = next(call for call in calls if "scripts.demo_bootstrap" in call)
        assert calls.index(starts[0]) < calls.index(bootstrap) < calls.index(starts[1])
    if failure is None:
        assert {item["path"] for item in evidence["suites"]} == set(gate.SUITES)


def test_cleanup_refuses_foreign_directory_before_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "command", lambda *_a, **_k: pytest.fail("Docker must not run"))
    with pytest.raises(ValueError, match="refusing cleanup"):
        gate.cleanup(["docker", "compose", "-p", "dev"], tmp_path / "012345abcdef", {})


def test_run_collision_never_starts_or_cleans_existing_project(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "resources", lambda *_: {"containers": "existing-id"})
    monkeypatch.setattr(gate, "command", lambda *_a, **_k: pytest.fail("Docker mutation forbidden"))
    with pytest.raises(ValueError, match="already exists"):
        gate.main(["--model-dir", str(tmp_path), "--run-id", "012345abcdef"])
    assert not (tmp_path / "logs").exists()


@pytest.mark.requires_extras
async def test_real_dispatcher_polling_creates_readiness_marker(tmp_path, monkeypatch):
    import asyncio

    from aiogram import Dispatcher

    from tests.e2e_core import bot_runtime

    marker = tmp_path / "polling"
    monkeypatch.setattr(bot_runtime, "POLLING_MARKER", marker)
    bot = bot_runtime.local_bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    await bot.get_me()
    assert not marker.exists()
    dispatcher = Dispatcher()
    task = asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False))
    try:
        async with asyncio.timeout(5):
            while not marker.exists():  # noqa: ASYNC110 - observing an external file boundary
                await asyncio.sleep(0.01)
        assert not task.done()
    finally:
        await dispatcher.stop_polling()
        await task


@pytest.mark.parametrize("enabled", [False, True])
def test_auxiliary_docker_labels_are_explicit_full_gate_only(monkeypatch, enabled):
    from tests.e2e_core.live_harness import full_gate_docker_args

    monkeypatch.setenv("E2E_RUN_ID", "012345abcdef")
    monkeypatch.setenv("E2E_FULL_GATE", "1" if enabled else "0")
    args = ("run", "--rm", "redis:8.10.1")
    expected = ["docker", "run"]
    if enabled:
        expected += ["--label", "rag.e2e.run=012345abcdef"]
    assert full_gate_docker_args(args) == [*expected, *args[1:]]
    assert full_gate_docker_args(("ps", "-a")) == ["docker", "ps", "-a"]


@pytest.mark.parametrize("owner", ["012345abcdef", "d760c1118ab6"])
def test_auxiliary_cleanup_rechecks_exact_owner(tmp_path, monkeypatch, owner):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    state = {"auxiliary_containers": "fixture-id"}
    monkeypatch.setattr(gate, "resources", lambda *_: dict(state))
    calls = []

    def command(args, _env, **_kwargs):
        calls.append(args)
        if "inspect" in args:
            return owner
        if args[:3] == ["docker", "rm", "-f"]:
            state.clear()
        return ""

    monkeypatch.setattr(gate, "command", command)
    args = ["docker", "compose", "-p", "rag-e2e-012345abcdef"]
    run_dir = tmp_path / "logs/e2e-full/012345abcdef"
    if owner == "012345abcdef":
        gate.cleanup(args, run_dir, {})
        assert ["docker", "rm", "-f", "fixture-id"] in calls
    else:
        with pytest.raises(ValueError, match="foreign fixture"):
            gate.cleanup(args, run_dir, {})
        assert not any("rm" in call or "down" in call for call in calls)


@pytest.mark.parametrize("restarts", [0, 1, 2])
def test_only_controlled_qdrant_restart_has_a_budget(monkeypatch, restarts):
    rows = [
        {
            "project": "rag-e2e-012345abcdef",
            "service": name,
            "status": "running",
            "health": "healthy",
            "restarts": restarts if name == "qdrant" else 0,
        }
        for name in gate.SERVICES
    ]
    monkeypatch.setattr(
        gate,
        "command",
        lambda args, _env: "ids" if "ps" in args else "\n".join(json.dumps(row) for row in rows),
    )
    if restarts > 1:
        with pytest.raises(ValueError):
            gate.service_snapshot(
                ["docker", "compose"], "rag-e2e-012345abcdef", {}, allow_qdrant_restart=True
            )
    else:
        assert (
            len(
                gate.service_snapshot(
                    ["docker", "compose"], "rag-e2e-012345abcdef", {}, allow_qdrant_restart=True
                )
            )
            == 6
        )
