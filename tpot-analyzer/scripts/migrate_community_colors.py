"""Migrate community colors from generic Material Design to iconography palette.

Reads config/community_iconography.json, picks the best color per community
for dark-background readability, and updates the community.color column.

Usage:
    .venv/bin/python3 -m scripts.migrate_community_colors
    .venv/bin/python3 -m scripts.migrate_community_colors --dry-run
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "archive_tweets.db"
ICON_PATH = ROOT / "config" / "community_iconography.json"

# Minimum perceived brightness for readability on #0a0a0a background.
# Formula: (0.299*R + 0.587*G + 0.114*B) / 255
MIN_BRIGHTNESS = 0.25


def perceived_brightness(hex_color: str) -> float:
    """Calculate perceived brightness (0-1) of a hex color."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def pick_best_color(colors: list[str], color_names: str) -> tuple[str, str]:
    """Pick the best color from the iconography palette for dark backgrounds.

    Prefers the primary (index 0). Falls back to secondary/tertiary if
    primary is too light. Returns (color, reason).
    """
    if not colors:
        return "#888888", "no colors defined"

    primary = colors[0]
    brightness = perceived_brightness(primary)

    if brightness <= 0.85:  # Most colors are fine
        # But check if it's TOO dark (near black)
        if brightness >= MIN_BRIGHTNESS:
            return primary, "primary"
        # Primary too dark — try secondary
        if len(colors) > 1:
            sec_bright = perceived_brightness(colors[1])
            if MIN_BRIGHTNESS <= sec_bright <= 0.85:
                return colors[1], "secondary (primary too dark)"
        # Fall back to a midtone version
        return primary, "primary (dark, no better option)"

    # Primary too light for dark background (cream, white, etc.)
    # Try secondary
    if len(colors) > 1:
        sec_bright = perceived_brightness(colors[1])
        if MIN_BRIGHTNESS <= sec_bright <= 0.85:
            return colors[1], f"secondary (primary too light: {brightness:.2f})"

    # Try tertiary
    if len(colors) > 2:
        ter_bright = perceived_brightness(colors[2])
        if MIN_BRIGHTNESS <= ter_bright <= 0.85:
            return colors[2], f"tertiary (primary+secondary too light)"

    # All too light — use primary anyway, it'll just be bright
    return primary, f"primary (all options light: {brightness:.2f})"


# Manual overrides for communities where the auto-picker fails on dark backgrounds.
# These are hand-picked to be: (a) true to the iconography spirit, (b) readable on #0a0a0a,
# (c) distinct from each other.
OVERRIDES = {
    # Primary #000080 is invisible on dark bg. Use parchment gold instead — "ink on parchment"
    "Internet-Intellectuals": "#F5DEB3",
    # Primary #4B0082 is too dark. Use a brighter violet that reads as contemplative.
    "Contemplative-Practitioners": "#7B68EE",
    # Primary #C0C0C0 is generic. Use a lighter slate blue — "crystalline precision"
    "AI-Safety": "#8DA4BF",
    # Primary #C0C0C0 again. Use a brighter titanium — "structural beams"
    "Tech-Intellectuals": "#A0B4C8",
    # Primary #808080 too muted. Use crimson accent — "ambitious crimson"
    "NYC-Institution-Builders": "#DC143C",
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Migrate community colors to iconography palette")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    args = parser.parse_args()

    with open(ICON_PATH) as f:
        iconography = json.load(f)["communities"]

    conn = sqlite3.connect(str(args.db_path))
    communities = conn.execute(
        "SELECT id, name, short_name, color FROM community ORDER BY name"
    ).fetchall()

    print(f"{'Community':<35} {'Old':<10} {'New':<10} {'Source':<40}")
    print("-" * 95)

    updates = []
    for cid, name, short_name, old_color in communities:
        icon = iconography.get(short_name)
        if not icon:
            print(f"{name:<35} {old_color:<10} {'—':<10} NO ICONOGRAPHY ENTRY")
            continue

        # Check manual overrides first
        if short_name in OVERRIDES:
            new_color = OVERRIDES[short_name]
            reason = "manual override (dark-bg readability)"
        else:
            new_color, reason = pick_best_color(icon["colors"], icon.get("color_names", ""))
        changed = old_color.lower() != new_color.lower()
        marker = " ←" if changed else ""
        print(f"{name:<35} {old_color:<10} {new_color:<10} {reason}{marker}")

        if changed:
            updates.append((new_color, cid))

    print()
    print(f"Total: {len(communities)} communities, {len(updates)} color changes")

    if args.dry_run:
        print("(dry run — no changes written)")
        return

    if not updates:
        print("Nothing to update.")
        return

    for new_color, cid in updates:
        conn.execute("UPDATE community SET color = ? WHERE id = ?", (new_color, cid))
    conn.commit()
    conn.close()
    print(f"Updated {len(updates)} community colors in DB.")
    print("Re-run export to propagate to public site.")


if __name__ == "__main__":
    main()
