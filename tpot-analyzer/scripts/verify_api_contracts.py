"""Verify frontend/backend API contract alignment."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from src.api.server import create_app


CHECK = "✓"
CROSS = "✗"


def _status(ok: bool, text: str) -> str:
    return f"{CHECK if ok else CROSS} {text}"


def _normalize_path(raw: str) -> str:
    path = raw.strip()
    if "http://localhost:5001" in path:
        path = path.split("http://localhost:5001", 1)[1]
    if "API_BASE_URL" in path:
        path = path.split("API_BASE_URL", 1)[1]

    # Keep from first slash onward, drop query parameters.
    slash = path.find("/")
    if slash >= 0:
        path = path[slash:]
    path = path.split("?", 1)[0]

    # Normalize template expressions and route placeholders.
    path = re.sub(r"\$\{[^}]+\}", "<param>", path)
    path = re.sub(r"<[^>]+>", "<param>", path)
    path = re.sub(r"/+", "/", path).rstrip("/")
    return path or "/"


def _extract_frontend_paths(project_root: Path) -> dict[str, list[str]]:
    source_files = [
        project_root / "graph-explorer" / "src" / "data.js",
        project_root / "graph-explorer" / "src" / "accountsApi.js",
        project_root / "graph-explorer" / "src" / "discoveryApi.js",
        project_root / "graph-explorer" / "src" / "logger.js",
    ]
    path_re = re.compile(r"(/api/[A-Za-z0-9_/$<>{}().?-]+|/health)")
    found: dict[str, list[str]] = {}

    for source_file in source_files:
        text = source_file.read_text(encoding="utf-8")
        for match in path_re.finditer(text):
            raw = match.group(1)
            normalized = _normalize_path(raw)
            found.setdefault(normalized, []).append(f"{source_file.relative_to(project_root)}:{text.count(chr(10), 0, match.start()) + 1}")
    return found


def _extract_backend_routes() -> set[str]:
    app = create_app({"TESTING": True})
    routes = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/") or rule.rule == "/health":
            routes.add(_normalize_path(rule.rule))
    return routes


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    frontend_map = _extract_frontend_paths(project_root)
    backend_routes = _extract_backend_routes()

    required_frontend_paths = sorted(frontend_map.keys())
    missing = [path for path in required_frontend_paths if path not in backend_routes]

    print("TPOT API Contract Verification")
    print("=" * 40)
    print(_status(True, f"Frontend contract paths detected: {len(required_frontend_paths)}"))
    print(_status(True, f"Backend API routes detected: {len(backend_routes)}"))
    print(_status(not missing, f"Contract gaps: {len(missing)}"))

    if missing:
        print("")
        print("Missing backend routes for frontend calls:")
        for path in missing:
            refs = ", ".join(frontend_map[path][:3])
            print(f"- {path}  (refs: {refs})")
    else:
        print("")
        print("All frontend API paths map to backend routes.")

    print("")
    print("Next steps:")
    print("1. If gaps exist, add backend routes or remove stale frontend calls.")
    print("2. Re-run this script after route changes.")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
