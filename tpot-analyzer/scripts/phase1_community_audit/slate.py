"""Curated 36-item pilot slate for the Phase 1 community-correctness audit."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _item(
    review_id: str,
    bucket: str,
    username: str,
    target_community_short_name: str,
    selection_reason: str,
    *,
    expected_judgment: str = "in",
    likely_confusions: Iterable[str] = (),
) -> Dict[str, Any]:
    return {
        "review_id": review_id,
        "bucket": bucket,
        "username": username,
        "target_community_short_name": target_community_short_name,
        "expected_judgment": expected_judgment,
        "likely_confusions": list(likely_confusions),
        "selection_reason": selection_reason,
    }


PHASE1_SLATE: List[Dict[str, Any]] = [
    _item("core-ai-creativity-abrakjamson", "core", "abrakjamson", "AI-Creativity", "High-confidence NMF member; legible creative-technologist profile."),
    _item("core-ai-safety-nunosempere", "core", "NunoSempere", "AI-Safety", "High-confidence NMF member; publicly legible EA/forecasting profile."),
    _item("core-collective-intelligence-technoshaman", "core", "technoshaman", "Collective-Intelligence", "High-confidence regen / collective-intelligence account with rich local tweet history."),
    _item("core-contemplative-nowtheo", "core", "nowtheo", "Contemplative-Practitioners", "High-confidence contemplative seed with clear first-person practice language."),
    _item("core-core-tpot-realpilleater", "core", "realpilleater", "Core-TPOT", "High-confidence core-scene account; useful test of subcultural legibility."),
    _item("core-highbies-lithros", "core", "Lithros", "highbies", "High-confidence Vibecamp / highbie account with enough local tweets for review."),
    _item("core-internet-intellectuals-drmaciver", "core", "DRMacIver", "Internet-Intellectuals", "High-confidence essayist / internet-intellectual seed with strong local text coverage."),
    _item("core-llm-whisperers-v01dpr1mr0s3", "core", "v01dpr1mr0s3", "LLM-Whisperers", "High-confidence LLM scene account with recent local tweets."),
    _item("core-nyc-institution-builders-danielgolliher", "core", "danielgolliher", "NYC-Institution-Builders", "High-confidence civic / New York institutional-builder account."),
    _item("core-qualia-archived-videos", "core", "archived_videos", "Qualia-Research", "High-confidence qualia-adjacent member from the current map."),
    _item("core-queer-tpot-annieposting", "core", "AnniePosting", "Queer-TPOT", "High-confidence queer-scene seed with clear stylistic signal."),
    _item("core-tft-lchoshen", "core", "LChoshen", "TfT-Coordination", "High-confidence tools-for-thought / coordination account from current NMF map."),
    _item("boundary-ai-safety-ohabryka", "boundary", "ohabryka", "AI-Safety", "Repeatedly split between AI-Safety and Tech-Intellectuals in current assignments.", likely_confusions=("Tech-Intellectuals", "Core-TPOT", "Internet-Intellectuals")),
    _item("boundary-qualia-bryan-johnson", "boundary", "bryan_johnson", "Qualia-Research", "Strong near-miss between qualia / self-experimentation and public techno-optimization.", likely_confusions=("Tech-Intellectuals", "Contemplative-Practitioners")),
    _item("boundary-llm-whisperers-plinz", "boundary", "Plinz", "LLM-Whisperers", "Current assignments tie between LLM-Whisperers and highbies.", likely_confusions=("highbies", "Tech-Intellectuals")),
    _item("boundary-contemplative-danallison", "boundary", "danallison", "Contemplative-Practitioners", "Current assignments put this account on the contemplative / quiet-creative boundary.", likely_confusions=("Quiet-Creatives",)),
    _item("boundary-relational-liquidprismata", "boundary", "liquidprismata", "Relational-Explorers", "Current assignments put this account on the relational / queer boundary.", likely_confusions=("Queer-TPOT", "Quiet-Creatives")),
    _item("boundary-tech-intellectuals-vamsi0x", "boundary", "vamsi0x", "Tech-Intellectuals", "Current assignments split between Tech-Intellectuals and TfT-Coordination.", likely_confusions=("TfT-Coordination", "Collective-Intelligence")),
    _item("boundary-collective-intelligence-rtk254", "boundary", "rtk254", "Collective-Intelligence", "Current assignments split between Collective-Intelligence and TfT-Coordination.", likely_confusions=("TfT-Coordination",)),
    _item("boundary-queer-tpot-toinpu", "boundary", "toinpu", "Queer-TPOT", "Current assignments split between Queer-TPOT and Internet-Intellectuals.", likely_confusions=("Internet-Intellectuals",)),
    _item("boundary-highbies-cxgonzalez", "boundary", "cxgonzalez", "highbies", "Current assignments put this account on the highbies / core boundary.", likely_confusions=("Core-TPOT", "Relational-Explorers")),
    _item("boundary-core-tpot-arizerner", "boundary", "AriZerner", "Core-TPOT", "Current assignments split between Core-TPOT and Tech-Intellectuals.", likely_confusions=("Tech-Intellectuals",)),
    _item("boundary-ai-creativity-abrleth", "boundary", "abrleth", "AI-Creativity", "Current assignments split between AI-Creativity and Quiet-Creatives.", likely_confusions=("Quiet-Creatives", "Internet-Intellectuals")),
    _item("boundary-internet-intellectuals-roberthaisfield", "boundary", "RobertHaisfield", "Internet-Intellectuals", "Current assignments split between Internet-Intellectuals and TfT-Coordination.", likely_confusions=("TfT-Coordination", "Tech-Intellectuals")),
    _item("hardneg-llm-whisperers-karpathy", "hard_negative", "karpathy", "LLM-Whisperers", "Mainstream AI research celebrity; plausible confounder for LLM-Whisperers but likely not socially embedded in TPOT.", expected_judgment="out", likely_confusions=("Tech-Intellectuals",)),
    _item("hardneg-llm-whisperers-emollick", "hard_negative", "emollick", "LLM-Whisperers", "AI educator and public AI commentator; topical near-miss without TPOT social embedding.", expected_judgment="out", likely_confusions=("Tech-Intellectuals",)),
    _item("hardneg-tech-intellectuals-pmarca", "hard_negative", "pmarca", "Tech-Intellectuals", "Public tech-intellectual / VC near-miss rather than TPOT insider.", expected_judgment="out", likely_confusions=("Internet-Intellectuals",)),
    _item("hardneg-tech-intellectuals-balajis", "hard_negative", "balajis", "Tech-Intellectuals", "Tech / network-state confounder with scene adjacency but likely outside the ontology.", expected_judgment="out", likely_confusions=("Internet-Intellectuals",)),
    _item("hardneg-internet-intellectuals-paulg", "hard_negative", "paulg", "Internet-Intellectuals", "Essayist / founder near-miss who looks ontologically close from topic and style.", expected_judgment="out", likely_confusions=("Tech-Intellectuals",)),
    _item("hardneg-tech-intellectuals-lexfridman", "hard_negative", "lexfridman", "Tech-Intellectuals", "High-visibility public intellectual in tech; strong near-miss rather than core TPOT member.", expected_judgment="out", likely_confusions=("Internet-Intellectuals",)),
    _item("hardneg-internet-intellectuals-noahpinion", "hard_negative", "Noahpinion", "Internet-Intellectuals", "Independent writer / newsletter confounder with style overlap but likely out of scene.", expected_judgment="out", likely_confusions=("Tech-Intellectuals",)),
    _item("hardneg-internet-intellectuals-dwarkesh", "hard_negative", "dwarkesh_sp", "Internet-Intellectuals", "Podcast / public intellectual confounder with adjacent audience but likely not ontology member.", expected_judgment="out", likely_confusions=("Tech-Intellectuals",)),
    _item("hardneg-contemplative-huberman", "hard_negative", "hubermanlab", "Contemplative-Practitioners", "Mainstream wellness / neuroscience confounder rather than TPOT contemplative account.", expected_judgment="out", likely_confusions=("Qualia-Research",)),
    _item("hardneg-qualia-deepak-chopra", "hard_negative", "DeepakChopra", "Qualia-Research", "Mainstream spiritual / wellness public figure; topical overlap without TPOT embedding.", expected_judgment="out", likely_confusions=("Contemplative-Practitioners",)),
    _item("hardneg-tech-intellectuals-naval", "hard_negative", "naval", "Tech-Intellectuals", "Tech-philosophy confounder and one-way attention magnet; useful hard negative.", expected_judgment="out", likely_confusions=("Internet-Intellectuals",)),
    _item("hardneg-ai-safety-demis", "hard_negative", "demishassabis", "AI-Safety", "AGI-adjacent public leader; topical overlap but likely outside TPOT internal ontology.", expected_judgment="out", likely_confusions=("LLM-Whisperers", "Tech-Intellectuals")),
]
