"""Slug generation and registry persistence for community URLs."""
from __future__ import annotations

import json
import re
from pathlib import Path


def slugify_name(name):
    """Convert community name to URL-safe slug."""
    s = name.lower()
    s = s.replace("&", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


def load_slug_registry(path):
    """Load slug registry from JSON file. Returns empty dict if file missing."""
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_slug_registry(path, registry):
    """Write slug registry to JSON file."""
    path = Path(path)
    with open(path, "w") as f:
        json.dump(registry, f, indent=2, sort_keys=True)


def assign_slugs(communities, registry):
    """Assign slugs to communities, preserving existing. Handles collisions."""
    updated = dict(registry)
    used_slugs = set(updated.values())
    for c in communities:
        cid = c["id"]
        if cid not in updated:
            base = slugify_name(c["name"])
            slug = base
            counter = 2
            while slug in used_slugs:
                slug = f"{base}-{counter}"
                counter += 1
            updated[cid] = slug
            used_slugs.add(slug)
    return updated
