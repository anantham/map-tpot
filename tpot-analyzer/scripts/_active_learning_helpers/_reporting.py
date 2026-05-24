"""Profile classification + inter-model agreement diagnostics."""
from __future__ import annotations


def profile_results(bits: dict[str, float]) -> str:
    """Classify account labeling results by confidence.

    Returns:
      - "no_signal" if bits is empty
      - "high" if top community > 60% OR any community > 40%
      - "ambiguous" if no community > 40%
    """
    if not bits:
        return "no_signal"

    top_pct = max(bits.values())

    if top_pct > 60.0:
        return "high"
    if top_pct <= 40.0:
        return "ambiguous"
    return "high"


def _extract_top_community(label_dict: dict) -> str | None:
    """Extract the top community from a single model's label output."""
    bits = label_dict.get("bits", [])
    best_community = None
    best_value = -999

    for tag in bits:
        parts = tag.split(":")
        if len(parts) == 3 and parts[0] == "bits":
            try:
                val = int(parts[2])
                if val > best_value:
                    best_value = val
                    best_community = parts[1]
            except ValueError:
                continue

    return best_community


def log_model_agreement(all_labels: list[list[dict]]) -> None:
    """Log inter-model agreement across all labeled tweets.

    all_labels: list of per-tweet lists, where each inner list has one dict
    per model (up to 3).

    Prints the percentage of tweets where all models agree on the top community.
    """
    if not all_labels:
        print("Model agreement: no tweets labeled")
        return

    total = 0
    agreed = 0

    for tweet_labels in all_labels:
        if len(tweet_labels) < 2:
            continue
        total += 1

        tops = [_extract_top_community(ld) for ld in tweet_labels]
        tops = [t for t in tops if t is not None]

        if len(tops) >= 2 and len(set(tops)) == 1:
            agreed += 1

    if total == 0:
        print("Model agreement: no multi-model tweets to compare")
        return

    pct = agreed / total * 100
    print(f"Model agreement: {agreed}/{total} tweets ({pct:.1f}%) — all models agree on top community")
