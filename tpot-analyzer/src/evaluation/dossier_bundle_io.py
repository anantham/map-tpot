"""Filesystem primitives for one private dossier execution bundle."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any

from .acquisition_manifest import canonical_json_hash, hash_plan_manifest


class DossierExecutionBundleError(ValueError):
    """Raised when a private execution bundle cannot be trusted."""


def json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DossierExecutionBundleError(
            "private artifact must contain canonical JSON values"
        ) from error


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_exclusive_write(path: Path, payload: bytes) -> None:
    """Publish complete bytes once, then fsync their directory entry."""
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = None
            destination.write(payload)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        fsync_directory(path.parent)
    except FileExistsError as error:
        raise DossierExecutionBundleError(
            f"private artifact already exists: {path.name}"
        ) from error
    except OSError as error:
        raise DossierExecutionBundleError(
            f"cannot atomically create private artifact {path.name}: {error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def resolved_output(output_dir: Path, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        parent = output_dir.parent.resolve(strict=True)
        candidate = output_dir.resolve(strict=False)
    except OSError as error:
        raise DossierExecutionBundleError(
            f"output must have an existing parent under resolved data/private: {error}"
        ) from error
    if not root.is_dir() or candidate == root or root not in candidate.parents:
        raise DossierExecutionBundleError(
            "output directory must be a new descendant of resolved data/private"
        )
    if root not in parent.parents and parent != root:
        raise DossierExecutionBundleError(
            "output parent escapes resolved data/private"
        )
    if output_dir.exists() or output_dir.is_symlink():
        raise DossierExecutionBundleError("private output directory must be new")
    return candidate


def load_sources(
    source_paths: dict[str, Path],
    expected_labels: set[str],
    preflight: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, dict[str, Any]]]:
    if set(source_paths) != expected_labels:
        raise DossierExecutionBundleError("source paths must be exactly plan/panel/price_card")
    payloads: dict[str, bytes] = {}
    objects: dict[str, dict[str, Any]] = {}
    for label, path in source_paths.items():
        try:
            payload = path.read_bytes()
            value = json.loads(payload)
        except (OSError, json.JSONDecodeError) as error:
            raise DossierExecutionBundleError(
                f"cannot preserve exact {label} source bytes"
            ) from error
        if not isinstance(value, dict):
            raise DossierExecutionBundleError(f"{label} source must be a JSON object")
        payloads[label] = payload
        objects[label] = value
    if (
        objects["plan"].get("plan_sha256") != preflight.get("plan_sha256")
        or hash_plan_manifest(objects["plan"]) != preflight.get("plan_sha256")
    ):
        raise DossierExecutionBundleError("plan source hash drifted after preflight")
    if hashlib.sha256(payloads["panel"]).hexdigest() != preflight.get(
        "selection_manifest_sha256"
    ):
        raise DossierExecutionBundleError("panel source hash drifted after preflight")
    if canonical_json_hash(objects["price_card"]) != preflight.get(
        "price_card_sha256"
    ):
        raise DossierExecutionBundleError("price-card source hash drifted after preflight")
    return payloads, objects


def create_bundle_directory(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        os.mkdir(path / "events", 0o700)
        os.chmod(path / "events", 0o700)
        fsync_directory(path.parent)
    except OSError as error:
        raise DossierExecutionBundleError(
            f"cannot create new private execution bundle: {error}"
        ) from error
