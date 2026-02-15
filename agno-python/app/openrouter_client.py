import os
from typing import Any

import requests


def call_openrouter(messages: list[dict[str, str]], model: str | None = None) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    selected_model = model or os.getenv(
        "OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free"
    )
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "")


def call_openrouter_message(
    messages: list[dict[str, Any]],
    model: str | None = None,
    reasoning_enabled: bool = True,
) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured.")

    selected_model = model or os.getenv(
        "OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free"
    )
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
        "reasoning": {"enabled": reasoning_enabled},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices", [])
    if not choices:
        return {"content": "", "reasoning_details": None, "model": selected_model}
    message = choices[0].get("message", {}) or {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "content": message.get("content", ""),
        "reasoning_details": message.get("reasoning_details"),
        "model": data.get("model", selected_model),
        "usage": usage,
        "provider_response_id": data.get("id"),
    }
