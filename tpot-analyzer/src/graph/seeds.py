"""Seed selection utilities."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, MutableMapping, Optional, Set, Tuple

_DEFAULT_PRESET_FILE = Path(__file__).resolve().parents[2] / "docs" / "seed_presets.json"
_SEED_STATE_FILE = Path(__file__).resolve().parents[2] / "config" / "graph_settings.json"
_HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_DEFAULT_PRESET_NAME = "adi_tpot"
_DEFAULT_DISCOVERY_WEIGHTS = {
    "neighbor_overlap": 0.4,
    "pagerank": 0.3,
    "community": 0.2,
    "path_distance": 0.1,
}
_DEFAULT_SETTINGS = {
    "alpha": 0.85,
    "discovery_weights": _DEFAULT_DISCOVERY_WEIGHTS,
    "max_distance": 3,
    "limit": 500,
    "auto_include_shadow": True,
}


def _read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _sanitize_handle(value: str | None) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip().lstrip("@").lower()
    if not cleaned:
        return None
    if not _HANDLE_PATTERN.match(cleaned):
        return None
    return cleaned


def _sanitize_seed_list(seeds: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for handle in seeds:
        cleaned = _sanitize_handle(handle)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def _load_presets() -> Dict[str, List[str]]:
    presets = _read_json(_DEFAULT_PRESET_FILE)
    if not isinstance(presets, MutableMapping):
        return {}

    normalized: Dict[str, List[str]] = {}
    for name, values in presets.items():
        if not isinstance(values, list):
            continue
        sanitized = _sanitize_seed_list(values)
        if sanitized:
            normalized[name] = sanitized
    return normalized


def _sanitize_settings(raw: MutableMapping) -> Dict[str, any]:
    settings = dict(_DEFAULT_SETTINGS)
    if isinstance(raw, MutableMapping):
        alpha = raw.get("alpha")
        if isinstance(alpha, (int, float)):
            settings["alpha"] = max(0.5, min(0.995, float(alpha)))
        dw = raw.get("discovery_weights")
        if isinstance(dw, MutableMapping):
            merged = dict(_DEFAULT_DISCOVERY_WEIGHTS)
            total = 0.0
            for key in merged.keys():
                value = dw.get(key)
                if isinstance(value, (int, float)):
                    merged[key] = max(0.0, float(value))
                    total += merged[key]
            if total > 0:
                merged = {k: v / total for k, v in merged.items()}
            settings["discovery_weights"] = merged
        max_distance = raw.get("max_distance")
        if isinstance(max_distance, (int, float)):
            settings["max_distance"] = int(max(1, min(6, max_distance)))
        limit = raw.get("limit")
        if isinstance(limit, (int, float)):
            settings["limit"] = int(max(50, min(5000, limit)))
        auto_shadow = raw.get("auto_include_shadow")
        if isinstance(auto_shadow, bool):
            settings["auto_include_shadow"] = auto_shadow
    return settings


def _load_user_state() -> Dict:
    state = _read_json(_SEED_STATE_FILE)
    if not isinstance(state, MutableMapping):
        state = {}
    lists = state.get("lists") or {}
    if not isinstance(lists, MutableMapping):
        lists = {}
    sanitized_lists = {
        str(name): _sanitize_seed_list(values or [])
        for name, values in lists.items()
        if _sanitize_seed_list(values or [])
    }
    settings = state.get("settings") or {}
    sanitized_settings = _sanitize_settings(settings)
    return {
        "active_list": state.get("active_list"),
        "lists": sanitized_lists,
        "updated_at": state.get("updated_at"),
        "settings": sanitized_settings,
    }


def _merge_seed_state() -> Dict[str, any]:
    presets = _load_presets()
    user_state = _load_user_state()
    lists: Dict[str, List[str]] = {}
    lists.update(presets)
    lists.update(user_state["lists"])

    active = user_state.get("active_list") or _DEFAULT_PRESET_NAME
    if active not in lists and lists:
        active = next(iter(lists.keys()))

    return {
        "active_list": active,
        "lists": lists,
        "updated_at": user_state.get("updated_at"),
        "preset_names": list(presets.keys()),
        "user_list_names": list(user_state["lists"].keys()),
        "settings": user_state.get("settings", _DEFAULT_SETTINGS),
    }


def get_seed_state() -> Dict[str, any]:
    """Return combined preset + user-defined seed lists."""
    return _merge_seed_state()


def save_seed_list(
    name: str,
    seeds: Iterable[str],
    *,
    set_active: bool = True,
) -> Dict[str, any]:
    """Persist a user-defined seed list and optionally set it active."""
    sanitized = _sanitize_seed_list(seeds)
    if not sanitized:
        raise ValueError("At least one valid handle is required.")

    state = _load_user_state()
    lists = state.get("lists") or {}
    lists[str(name)] = sanitized
    state["lists"] = lists

    if set_active:
        state["active_list"] = str(name)

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(_SEED_STATE_FILE, {
        "active_list": state.get("active_list"),
        "lists": state.get("lists"),
        "settings": state.get("settings", _DEFAULT_SETTINGS),
        "updated_at": state.get("updated_at"),
    })
    return _merge_seed_state()


def set_active_seed_list(name: str) -> Dict[str, any]:
    """Mark an existing seed list (preset or user) as active."""
    merged = _merge_seed_state()
    if name not in merged["lists"]:
        raise ValueError(f"Unknown seed list '{name}'")

    state = _load_user_state()
    state["active_list"] = name
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(_SEED_STATE_FILE, {
        "active_list": state.get("active_list"),
        "lists": state.get("lists"),
        "settings": state.get("settings", _DEFAULT_SETTINGS),
        "updated_at": state.get("updated_at"),
    })
    return _merge_seed_state()


def extract_usernames_from_html(html: str) -> List[str]:
    """Pull Twitter usernames from list HTML or text."""

    pattern = re.compile(r"@([A-Za-z0-9_]{1,15})")
    usernames = {match.group(1).lower() for match in pattern.finditer(html)}
    # Sort alphabetically while preferring handles without underscores.
    return sorted(usernames, key=lambda u: (u.replace("_", ""), u.count("_"), u))


def load_seed_candidates(
    *,
    additional: Iterable[str] = (),
    preset: Optional[str] = None,
) -> Set[str]:
    """Return combined seed set (active list + user provided)."""

    seed_state = _merge_seed_state()
    target = preset or seed_state["active_list"]
    active_seeds = seed_state["lists"].get(target, [])

    seeds = set(active_seeds)
    seeds.update(handle.lower() for handle in additional if handle)
    return {handle for handle in seeds if _HANDLE_PATTERN.match(handle)}


DEFAULT_SEEDS: Set[str] = set(load_seed_candidates())


def get_graph_settings() -> Dict[str, any]:
    """Return merged seed + settings data."""
    return _merge_seed_state()


def update_graph_settings(new_settings: MutableMapping) -> Dict[str, any]:
    if not isinstance(new_settings, MutableMapping):
        raise ValueError("settings must be an object")
    state = _load_user_state()
    state_settings = state.get("settings", _DEFAULT_SETTINGS)
    merged = dict(state_settings)
    sanitized = _sanitize_settings({**merged, **new_settings})
    state["settings"] = sanitized
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(_SEED_STATE_FILE, {
        "active_list": state.get("active_list"),
        "lists": state.get("lists"),
        "settings": state.get("settings"),
        "updated_at": state.get("updated_at"),
    })
    return _merge_seed_state()
