from pathlib import Path

from scripts import check_test_tracking


def test_is_test_path_recognizes_tests_dir() -> None:
    assert check_test_tracking._is_test_path(Path("tests/unit/test_x.py"))


def test_is_test_path_recognizes_frontend_pattern() -> None:
    assert check_test_tracking._is_test_path(Path("mini_app/frontend/src/main.test.tsx"))


def test_is_test_path_ignores_non_tests() -> None:
    assert not check_test_tracking._is_test_path(Path("src/services/runtime.py"))


def test_is_inside_nested_repo_detects_embedded_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "vendor" / "tool").mkdir(parents=True)
    (repo_root / "vendor" / "tool" / ".git").mkdir()
    candidate = Path("vendor/tool/tests/test_demo.py")
    assert check_test_tracking._is_inside_nested_repo(candidate, repo_root)


def test_find_untracked_tests_filters_nested_repo_and_non_tests(
    monkeypatch: object, tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "nested").mkdir()
    (repo_root / "nested" / ".git").mkdir()

    def fake_git_untracked(_: Path) -> list[Path]:
        return [
            Path("tests/unit/test_a.py"),
            Path("docs/README.md"),
            Path("nested/tests/test_b.py"),
            Path("mini_app/frontend/src/__tests__/App.test.tsx"),
        ]

    monkeypatch.setattr(check_test_tracking, "_git_untracked", fake_git_untracked)
    offenders = check_test_tracking.find_untracked_tests(repo_root)
    assert offenders == [
        Path("mini_app/frontend/src/__tests__/App.test.tsx"),
        Path("tests/unit/test_a.py"),
    ]
