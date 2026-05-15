from pathlib import Path


def test_deploy_vps_script_is_not_public_repo_surface() -> None:
    assert not Path("scripts/deploy-vps.sh").exists()
