"""Guard against image tag drift between compose and k8s core services.

NOTE: k8s manifests live under ``archive/k8s/`` and are not part of the
primary runtime path (Docker Compose is the primary runtime).  The drift
guard is kept as a skipped placeholder so it can be re-enabled when k8s
parity is actively maintained.  See DOCKER.md and README.md for the
compose-first runtime contract.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(
    reason=(
        "k8s manifests are archived under archive/k8s/ and not part of the "
        "primary runtime path; drift guard deferred until k8s parity is actively "
        "maintained (#2718)"
    )
)
def test_k8s_image_matches_compose() -> None:  # pragma: no cover
    """Placeholder: image-version sync between compose.yml and archive/k8s/."""
