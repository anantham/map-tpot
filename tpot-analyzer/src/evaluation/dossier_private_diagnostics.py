"""Privacy-safe diagnostics after a dossier live boundary is entered."""
from __future__ import annotations

import hashlib

from .dossier_evidence_artifact import DossierEvidenceArtifactError
from .dossier_execution_bundle import (
    DossierExecutionBundle,
    DossierExecutionBundleError,
)
from .dossier_snapshot_transform import DossierSnapshotTransformError


_PRIVATE_DETAIL_ERRORS = (
    DossierEvidenceArtifactError,
    DossierExecutionBundleError,
    DossierSnapshotTransformError,
)


def record_post_network_failure(
    bundle: DossierExecutionBundle,
    phase: str,
    error: Exception,
) -> bool:
    """Persist a private diagnostic without trusting arbitrary messages."""
    try:
        message = str(error)
    except Exception:
        message = "unrenderable exception message"
    diagnostic = {
        "schema_version": 1,
        "kind": "twitterapiio-dossier-post-network-error",
        "phase": phase,
        "error_type": type(error).__name__,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }
    if isinstance(error, _PRIVATE_DETAIL_ERRORS):
        diagnostic["detail"] = message
    try:
        bundle.write_json("post-network-error.json", diagnostic)
    except Exception:
        return False
    return True
