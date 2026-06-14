"""Pluggable LLM provider.

The default provider is `stub` — deterministic, offline, dependency-free.
Set LLM_PROVIDER=openai|anthropic and provide an API key to use a real
model. Step config passes `prompt`, `system`, `temperature`, `model`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from flowforge.core.config import get_settings


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: Dict[str, int]
    raw: Optional[Dict[str, Any]] = None


class LLMError(RuntimeError):
    pass


def _stub_completion(prompt: str, system: str, temperature: float, model: str) -> LLMResponse:
    """Deterministic offline stand-in. Echoes prompt with a stable hash
    so callers can verify routing without paying for tokens.
    """
    digest = hashlib.sha256(f"{system}|{prompt}".encode("utf-8")).hexdigest()[:8]
    snippet = prompt.strip().splitlines()[0][:120] if prompt.strip() else "(empty)"
    text = f"[stub:{model}] {digest} :: {snippet}"
    return LLMResponse(
        text=text,
        model=model,
        provider="stub",
        usage={"prompt_tokens": len(prompt), "completion_tokens": 32, "total_tokens": len(prompt) + 32},
    )


def _openai_completion(prompt: str, system: str, temperature: float, model: str, api_key: str) -> LLMResponse:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("openai package not installed") from exc

    client = OpenAI(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
    text = resp.choices[0].message.content or ""
    usage = {
        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
        "total_tokens": getattr(resp.usage, "total_tokens", 0) if resp.usage else 0,
    }
    return LLMResponse(text=text, model=model, provider="openai", usage=usage)


def _anthropic_completion(prompt: str, system: str, temperature: float, model: str, api_key: str) -> LLMResponse:
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMError("anthropic package not installed") from exc

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system or "",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text
    usage = {
        "prompt_tokens": resp.usage.input_tokens,
        "completion_tokens": resp.usage.output_tokens,
        "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
    }
    return LLMResponse(text=text, model=model, provider="anthropic", usage=usage)


def complete(
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.2,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMResponse:
    settings = get_settings()
    prov = (provider or settings.llm_provider).lower()
    chosen_model = model or settings.llm_default_model
    key = api_key or settings.llm_api_key

    if prov == "stub":
        return _stub_completion(prompt, system, temperature, chosen_model)
    if prov == "openai":
        if not key:
            raise LLMError("OPENAI api key missing (set LLM_API_KEY or pass api_key)")
        return _openai_completion(prompt, system, temperature, chosen_model or settings.llm_openai_model, key)
    if prov == "anthropic":
        if not key:
            raise LLMError("ANTHROPIC api key missing (set LLM_API_KEY or pass api_key)")
        return _anthropic_completion(prompt, system, temperature, chosen_model or settings.llm_anthropic_model, key)
    raise LLMError(f"unknown LLM provider: {prov!r}")


def list_models(provider: Optional[str] = None) -> Dict[str, Any]:
    settings = get_settings()
    return {
        "provider": (provider or settings.llm_provider).lower(),
        "models": {
            "stub": [settings.llm_default_model],
            "openai": [settings.llm_openai_model],
            "anthropic": [settings.llm_anthropic_model],
        }.get((provider or settings.llm_provider).lower(), []),
    }
