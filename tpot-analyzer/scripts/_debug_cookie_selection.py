"""Select owner-only JSON credentials before debug tooling starts any activity."""
from pathlib import Path
from typing import Callable

from src.shadow.cookie_store import load_cookies


def select_cookie_path(explicit: Path | None = None, *, secrets_dir: Path = Path("secrets"),
                       prompt: Callable[[str], str] = input) -> Path:
    """Validate JSON credentials; retired pickle cookies must be recaptured."""
    if explicit is not None:
        load_cookies(explicit)
        return explicit
    candidates = sorted(secrets_dir.glob("*.json"))
    if not candidates:
        raise ValueError("No JSON cookies found; recapture with scripts/setup_cookies.py. Legacy cookies cannot be migrated.")
    # A malformed candidate fails closed instead of quietly choosing another identity.
    for candidate in candidates:
        load_cookies(candidate)
    if len(candidates) == 1:
        return candidates[0]
    print("Validated JSON cookie files:")
    for index, candidate in enumerate(candidates, 1):
        print(f"  {index}. {candidate.name}")
    try:
        index = int(prompt(f"Select cookie file [1-{len(candidates)}]: ").strip()) - 1
    except (ValueError, EOFError, KeyboardInterrupt) as exc:
        raise ValueError("Invalid or cancelled JSON cookie selection") from exc
    if not 0 <= index < len(candidates):
        raise ValueError("JSON cookie selection is outside the listed range")
    selected = candidates[index]
    load_cookies(selected)
    return selected
