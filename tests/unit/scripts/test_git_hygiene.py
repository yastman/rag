from pathlib import Path


def test_git_hygiene_uses_dev_default_branch() -> None:
    text = Path("scripts/git_hygiene.py").read_text(encoding="utf-8")
    assert 'DEFAULT_BASE_BRANCH = "dev"' in text


def test_repo_cleanup_uses_dev_default_branch() -> None:
    text = Path("scripts/repo_cleanup.sh").read_text(encoding="utf-8")
    assert (
        'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text or 'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text
    )
