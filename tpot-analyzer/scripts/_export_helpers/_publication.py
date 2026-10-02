"""Explicit public-field projection and digest of reviewable candidate bytes."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "publication_fields.json"
MAX_EXPORT_BYTES = 32 * 1024 * 1024


def project_public_fields(value, schema, definitions: dict, *, strict: bool = False, depth: int = 0):
    if depth > 24:
        raise ValueError("publication payload exceeds nesting limit")
    if isinstance(schema, str):
        if value is None and schema.endswith("?"):
            return None
        kind = schema.rstrip("?")
        if kind == "string" and isinstance(value, str) and len(value) <= 100_000:
            return value
        if kind == "number" and type(value) in (int, float) and math.isfinite(value):
            return value
        raise ValueError(f"publication field must be bounded {schema}")
    if isinstance(schema, list):
        if not isinstance(value, list) or len(value) > 100_000:
            raise ValueError("publication field must be a bounded array")
        return [project_public_fields(item, schema[0], definitions, strict=strict, depth=depth + 1) for item in value]
    if "$ref" in schema:
        return project_public_fields(value, definitions[schema["$ref"]], definitions, strict=strict, depth=depth + 1)
    if not isinstance(value, dict) or len(value) > 100_000:
        raise ValueError("publication field must be a bounded object")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 256 or key in {"__proto__", "constructor", "prototype"}:
            raise ValueError("publication field has an invalid key")
        field_schema = schema.get(key, schema.get("*"))
        if field_schema is None:
            if strict:
                raise ValueError(f"publication field is not allowlisted: {key}")
            continue
        result[key] = project_public_fields(item, field_schema, definitions, strict=strict, depth=depth + 1)
    return result


def sanitize_public_payloads(data: dict, search: dict) -> tuple[dict, dict]:
    policy = json.loads(POLICY_PATH.read_text())
    definitions = policy["definitions"]
    if not {"communities", "accounts", "meta"} <= set(data):
        raise ValueError("publication data is missing root fields")
    if any(not re.fullmatch(r"[a-z0-9_]{1,15}", handle) for handle in search):
        raise ValueError("publication search keys must be normalized handles")
    return (project_public_fields(data, policy["data"], definitions),
            project_public_fields(search, policy["search"], definitions))


def candidate_digest(data_bytes: bytes, search_bytes: bytes) -> str:
    hashes = [hashlib.sha256(body).hexdigest() for body in (POLICY_PATH.read_bytes(), data_bytes, search_bytes)]
    return hashlib.sha256(("\n".join(hashes) + "\n").encode("ascii")).hexdigest()


def _atomic_write(path: Path, body: bytes) -> None:
    if path.is_symlink():
        raise ValueError("publication candidate destination must not be a symlink")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_public_candidate(output_dir: Path, data: dict, search: dict) -> dict:
    """Write a local candidate and an unapproved manifest; never publish it."""
    data, search = sanitize_public_payloads(data, search)
    bodies = [json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() for payload in (data, search)]
    if any(len(body) > MAX_EXPORT_BYTES for body in bodies):
        raise ValueError("publication candidate exceeds byte limit")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "policy": "public-site-v1", "status": "unapproved",
                "export_digest": candidate_digest(*bodies),
                "files": {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                          for name, body in zip(("data.json", "search.json"), bodies)}}
    for name, body in zip(("data.json", "search.json"), bodies):
        _atomic_write(output_dir / name, body)
    _atomic_write(output_dir / "publication-manifest.json", json.dumps(manifest, indent=2).encode())
    return manifest
