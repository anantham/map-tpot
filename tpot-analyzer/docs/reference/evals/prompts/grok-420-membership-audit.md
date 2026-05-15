You are an external auditor of Twitter/X social-scene membership.

Task:
Assess this account's likely membership in a TPOT-style ontology without using
my current graph placement, current community assignment, or current label.

Important rules:
- Do not optimize for politeness or ambiguity.
- Distinguish `in`, `adjacent`, `out`, and `uncertain`.
- If the account spans multiple scenes, say so.
- Base your answer on publicly legible posting style, topics, social scene,
  recurring references, and likely audience.
- Do not assume that "talks about AI" implies `LLM-Whisperers`.
- Do not assume that "talks about meditation" implies
  `Contemplative-Practitioners`.
- If the account is famous and broadly followed but not socially embedded in
  this scene, mark that clearly.

Ontology:
{{community_definitions}}

Account:
- Name/handle: {{account_handle}}
- Bio: {{bio}}
- Sample posts:
{{sample_posts}}

Return JSON only:
{
  "tpot_status": "in|adjacent|out|uncertain",
  "top_communities": [
    {"community": "NAME", "score": 0.0},
    {"community": "NAME", "score": 0.0},
    {"community": "NAME", "score": 0.0}
  ],
  "bridge_account": true,
  "confidence": 0.0,
  "rationale": "2-4 sentences",
  "evidence_signals": [
    "short phrase",
    "short phrase",
    "short phrase"
  ],
  "main_confusions": ["NAME", "NAME"],
  "why_not_in": "only if status is adjacent/out/uncertain"
}

