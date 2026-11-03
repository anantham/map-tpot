"""Fail-closed OpenRouter catalog, completion, and cost receipts."""
from __future__ import annotations

import math
import time
from typing import Any

import httpx

from scripts.label_tweets_ensemble import parse_label_json

CATALOG_URL = "https://openrouter.ai/api/v1/models"
COMPLETION_URL = "https://openrouter.ai/api/v1/chat/completions"


def load_catalog(client: httpx.Client, models: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    response = client.get(CATALOG_URL)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        keys = sorted(payload) if isinstance(payload, dict) else str(type(payload))
        raise ValueError(f"unexpected model catalog keys: {keys}")
    indexed = {item.get("id"): item for item in payload["data"] if isinstance(item, dict)}
    missing = [model for model in models if model not in indexed]
    if missing:
        raise ValueError(f"approved model(s) absent from live catalog: {missing}")
    return {model: indexed[model] for model in models}


def pricing_for(item: dict[str, Any]) -> dict[str, float]:
    pricing = item.get("pricing")
    if not isinstance(pricing, dict):
        raise ValueError(f"model {item.get('id')} has no pricing object")
    try:
        return {
            "promptPerToken": float(pricing["prompt"]),
            "completionPerToken": float(pricing["completion"]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"model {item.get('id')} has invalid prompt/completion pricing") from error


def call_model(
    client: httpx.Client,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for attempt in range(4):
        response = client.post(
            COMPLETION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 800,
            },
        )
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < 3:
                time.sleep(2**attempt)
                continue
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"{model} response is not an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError(f"{model} response missing choices; keys={sorted(payload)}")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ValueError(f"{model} response missing message content; keys={sorted(payload)}")
        parsed = parse_label_json(content)
        if parsed is None:
            raise ValueError(f"{model} returned unparseable label JSON")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return parsed, {
            "responseId": payload.get("id"),
            "responseModel": payload.get("model"),
            "topLevelKeys": sorted(payload),
            "usageKeys": sorted(usage),
            "promptTokens": usage.get("prompt_tokens"),
            "completionTokens": usage.get("completion_tokens"),
            "totalTokens": usage.get("total_tokens"),
            "reportedCostUsd": usage.get("cost"),
        }
    raise RuntimeError(f"{model} exhausted retries")


def estimated_cost(prompts: list[tuple[str, str]], catalog: dict[str, dict[str, Any]]) -> float:
    total = 0.0
    for system_prompt, user_prompt in prompts:
        prompt_tokens = math.ceil((len(system_prompt) + len(user_prompt)) / 4) + 500
        for item in catalog.values():
            pricing = pricing_for(item)
            total += prompt_tokens * pricing["promptPerToken"]
            total += 800 * pricing["completionPerToken"]
    return total


def actual_cost(receipt: dict[str, Any], pricing: dict[str, float]) -> float:
    reported = receipt.get("reportedCostUsd")
    if isinstance(reported, (int, float)):
        return float(reported)
    prompt = receipt.get("promptTokens")
    completion = receipt.get("completionTokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        raise ValueError("response has neither reported cost nor integer token usage")
    return prompt * pricing["promptPerToken"] + completion * pricing["completionPerToken"]
