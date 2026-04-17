from pathlib import Path


def test_git_hygiene_uses_dev_default_branch() -> None:
    text = Path("scripts/git_hygiene.py").read_text(encoding="utf-8")
    assert 'DEFAULT_BASE_BRANCH = "dev"' in text


def test_git_hygiene_protects_configured_base_branch() -> None:
    text = Path("scripts/git_hygiene.py").read_text(encoding="utf-8")
    assert 'protected = {base_branch, "main", "master", "develop"}' in text


def test_repo_cleanup_uses_dev_default_branch() -> None:
    text = Path("scripts/repo_cleanup.sh").read_text(encoding="utf-8")
    assert (
        'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text or 'MAIN_BRANCH="${MAIN_BRANCH:-dev}"' in text
    )


def test_repo_cleanup_filters_base_branch_by_exact_match() -> None:
    text = Path("scripts/repo_cleanup.sh").read_text(encoding="utf-8")
    assert 'grep -v "$MAIN_BRANCH"' not in text
    assert '[ "$branch" = "$MAIN_BRANCH" ] && continue' in text
