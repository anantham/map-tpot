You are helping design a hard-negative benchmark for a TPOT community map.

Goal:
Suggest additional accounts that are plausible confounders for this ontology:
accounts that are close in topic, vibe, audience, or structural proximity, but
should probably NOT be labeled as true members of the target communities.

Important rules:
- Do not give easy negatives like random brands or politicians unless they are
  genuinely plausible confounders.
- Prefer near-miss accounts.
- Group suggestions by which community they could be confused with.
- For each suggestion, explain why it is a hard negative rather than an obvious
  negative.
- Flag any suggestions that might actually be true positives or bridges.
- Avoid duplicates of the current draft set.

Ontology:
{{community_definitions}}

Current draft hard negatives:
{{selected_hard_negatives}}

Return JSON only:
{
  "hard_negative_candidates": [
    {
      "account": "NAME OR HANDLE",
      "likely_confused_with": ["COMMUNITY", "COMMUNITY"],
      "why_hard_negative": "1-2 sentences",
      "risk_of_being_true_positive": "low|medium|high"
    }
  ]
}
