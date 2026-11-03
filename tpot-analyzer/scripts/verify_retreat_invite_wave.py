#!/usr/bin/env python3
"""Read-only checks for an invite wave; not a fit or source-truth evaluator."""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--preserved-manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--expected-count", type=int, default=20)
    args = parser.parse_args()
    failures = []

    def check(name, condition, metric):
        print(f"{'✓' if condition else '✗'} {name}: {metric}")
        if not condition:
            failures.append(name)

    try:
        packet = json.loads(args.packet.read_text())
        graph = json.loads(args.graph.read_text())
        review = args.review.read_text()
        manifest_hash = hashlib.sha256(args.preserved_manifest.read_bytes()).hexdigest()
        cards = packet["cards"]
        exclusion_groups = packet["known_contact_exclusions"]
        if not isinstance(cards, list) or not isinstance(graph, list):
            raise ValueError("cards and graph must be arrays")
        if not isinstance(exclusion_groups, dict):
            raise ValueError("exclusions must be grouped arrays")
        if any(not isinstance(c, dict) for c in cards + graph):
            raise ValueError("all card and graph rows must be objects")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"✗ Input readiness: {type(error).__name__}")
        print("Next: check explicit file paths and JSON shapes; no store was opened.")
        return 1

    handles = [str(c.get("handle", "")).lower() for c in cards]
    ids = [str(c.get("account_id", "")) for c in cards]
    captured = {str(c.get("account_id")): c for c in graph}
    excluded = {h.lower() for group in exclusion_groups.values() for h in group}
    check("Nonempty expected corpus", len(cards) == args.expected_count > 0,
          f"{len(cards)} cards, expected {args.expected_count}; {len(graph)} graph rows")
    check("Unique numeric identities",
          len(set(ids)) == len(cards) and all(re.fullmatch(r"[0-9]+", i) for i in ids),
          f"{len(set(ids))} unique numeric IDs")
    check("Unique valid handles",
          len(set(handles)) == len(cards) and all(re.fullmatch(r"[a-z0-9_]{1,15}", h) for h in handles),
          f"{len(set(handles))} unique handles")
    identity_matches = sum(
        i in captured and str(captured[i].get("handle", "")).lower() == h
        for i, h in zip(ids, handles)
    )
    check("Captured handle and ID match", identity_matches == len(cards),
          f"{identity_matches}/{len(cards)} captured identities")
    path_matches = sum(
        c.get("graph", {}).get("direction") == "seed follows candidate"
        and bool(c.get("graph", {}).get("seed_handles"))
        and sorted(c["graph"]["seed_handles"])
        == sorted(captured.get(i, {}).get("seed_paths", {}))
        for c, i in zip(cards, ids)
    )
    check("Directed graph routing retained", path_matches == len(cards),
          f"{path_matches}/{len(cards)} nonempty matching seed paths")
    overlap = set(handles) & excluded
    check("Saved known exclusions respected", not overlap,
          f"{len(overlap)} overlaps; {len(excluded)} excluded handles")
    complete = sum(
        bool(c.get("name")) and bool(c.get("review_evidence"))
        and bool(c.get("review_fit")) and bool(c.get("identity_binding", {}).get("evidence"))
        and bool(c.get("geography", {}).get("evidence"))
        and all(urlparse(c.get(key, "")).scheme == "https"
                for key in ("profile_url", "review_website"))
        and urlparse(c.get("artifact", {}).get("url", "")).scheme == "https"
        for c in cards
    )
    check("Evidence fields present, not truth-verified", complete == len(cards),
          f"{complete}/{len(cards)} complete records")
    draft_ok = sum(
        c.get("invitation_message")
        == c.get("invitation_opener", "") + "\n" + packet["invitation_url"] + "\n" + packet["closing"]
        and len(c.get("invitation_opener", "").split()) <= 55
        and not re.search(r"—|your work|interesting perspective|exactly the kind of",
                          c.get("invitation_message", ""), re.IGNORECASE)
        for c in cards
    )
    check("Short drafts and saved style rules", draft_ok == len(cards),
          f"{draft_ok}/{len(cards)} valid; max opener {max((len(c.get('invitation_opener', '').split()) for c in cards), default=0)} words")
    unchecked = sum(c.get("outreach_status") == "unchecked"
                    and c.get("send_eligible") is False for c in cards)
    check("No unsupported send eligibility", unchecked == len(cards),
          f"{unchecked}/{len(cards)} unchecked, unsent review candidates")
    review_matches = sum(
        f"[@{c.get('handle')}]({c.get('profile_url')})" in review
        and c.get("invitation_opener", "") in review for c in cards
    )
    check("Review sheet includes every draft", review_matches == len(cards),
          f"{review_matches}/{len(cards)} cards; {len(review.splitlines())} lines")
    scope = packet.get("scope", {})
    check("Recorded research-only scope",
          scope.get("new_paid_api_calls") == 0 and scope.get("messages_sent") == 0
          and scope.get("total_approved_batch_cap_usd") == 20,
          "0 new paid calls, 0 sends, $20 approved cap; recorded scope, not provider receipt")
    check("Preserved prior manifest", manifest_hash == args.manifest_sha256,
          "SHA256 matches" if manifest_hash == args.manifest_sha256 else "SHA256 differs")
    private = all(p.stat().st_mode & 0o077 == 0 for p in (args.packet, args.review, args.packet.parent))
    check("Private packet permissions", private, "owner-only" if private else "group/other access exists")
    print("Routing buckets:", dict(Counter(c.get("geography", {}).get("priority_bucket") for c in cards)))
    print("This script does not prove fit, current location, source truth or prior-contact clearance.")
    print("Next: review the cited public work and check each individual outreach chat before sending.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())

