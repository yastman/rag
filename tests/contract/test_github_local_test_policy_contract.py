from pathlib import Path


WORKFLOWS = Path(".github/workflows")
HOSTED_TEST_WORKFLOWS = (
    "core-tests.yml",
    "trusted-heavy.yml",
    "nightly-heavy.yml",
)


def test_hosted_test_workflows_are_absent() -> None:
    for name in HOSTED_TEST_WORKFLOWS:
        assert not (WORKFLOWS / name).exists(), f"hosted test workflow remains: {name}"


def test_github_workflows_do_not_run_pytest_or_make_test() -> None:
    workflow_paths = (*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "pytest" not in text, f"{path} runs pytest; tests must run locally"
        assert "make test" not in text, f"{path} runs make test; tests must run locally"
