"""Read-only source-preservation checks for the all-account outreach CSV."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook


def key(value):
    return str(value or "").strip().lstrip("@").lower()


def verify(args):
    book = load_workbook(args.original, read_only=True, data_only=True)
    original = [["" if v is None else v for v in r] for r in book["Contacts"].values]
    book.close()
    with open(args.contacts, newline="", encoding="utf-8-sig") as stream:
        latest = list(csv.DictReader(stream))
    with open(args.csv, newline="", encoding="utf-8-sig") as stream:
        exported = list(csv.reader(stream))
    def unescape(value):
        return value[1:] if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@")) else value
    master = [[unescape(v) for v in r] for r in exported]
    graph = json.loads(Path(args.graph).read_text())
    headers, old_headers = master[0], original[0]
    records = [dict(zip(headers, r)) for r in master[1:]]
    by_handle = {key(r["handle"]): r for r in records}

    def check(condition, label):
        print(("✓ " if condition else "✗ ") + label)
        if not condition:
            raise ValueError(label)

    check(len(records) == len(graph) == 18510, "18,510 captured accounts included")
    check(len(by_handle) == len(records), "No duplicate handles")
    check(len({r["account_id"] for r in records}) == len(records), "No duplicate IDs")
    check(all(isinstance(r["account_id"], str) for r in records), "IDs remain text")
    check({(r["account_id"], key(r["handle"])) for r in records} ==
          {(g["account_id"], key(g["handle"])) for g in graph}, "Exact captured identities")
    check(all(all(str(by_handle[key(r["handle"])][h]) == v for h, v in r.items()) for r in latest),
          f"All {len(latest)} latest contact rows preserved exactly")
    latest_handles = {key(r["handle"]) for r in latest}
    changed_columns = set(latest[0]) | {"contact_status_source"}
    preserved = True
    for row in original[1:]:
        old = dict(zip(old_headers, row))
        current = by_handle[key(old["handle"])]
        for h in old_headers:
            if key(old["handle"]) not in latest_handles or h not in changed_columns:
                preserved = preserved and str(current[h]) == str(old[h])
    check(preserved, f"All {len(original)-1} saved drafts and research records preserved")
    check(sum(bool(r["draft_message"]) for r in records) == 910, "910 drafts, 17,600 undrafted")
    check(sum(bool(r["captured_website"]) for r in records) == 13614, "13,614 captured website links")
    def csv_safe(value):
        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
        return str(value)
    check(exported == [[csv_safe(v) for v in r] for r in master],
          "CSV roundtrip preserves text, with formula-like text escaped")
    fields = {"captured_bio":"bio", "captured_location":"location",
              "captured_website":"website", "captured_at":"captured_at"}
    check(all(by_handle[key(g["handle"])][h] == str(g.get(s) or "")
              for g in graph for h, s in fields.items()), "Captured profiles and timestamps preserved verbatim")
    check(all(len(r) == 41 for r in exported), "41 columns on every CSV row")
    print("Research stages:", dict(Counter(r["research_stage"] for r in records)))
    print("Next: filter research_stage. Import account_id as text. Refresh contact status before outreach.")
    print("No files changed. This checks consolidation, not event fit or outreach clearance.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("csv", "original", "contacts", "graph"):
        parser.add_argument("--" + name, type=Path, required=True)
    verify(parser.parse_args())
