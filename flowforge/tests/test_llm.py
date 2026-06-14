"""LLM service tests (stub provider)."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "stub")

from flowforge.services.llm import complete, list_models


def test_stub_complete_is_deterministic():
    a = complete("hello", system="s", model="stub-1")
    b = complete("hello", system="s", model="stub-1")
    assert a.text == b.text
    assert a.provider == "stub"
    assert a.model == "stub-1"


def test_stub_complete_differs_by_input():
    a = complete("foo", system="s", model="stub-1")
    b = complete("bar", system="s", model="stub-1")
    assert a.text != b.text


def test_list_models():
    info = list_models(provider="stub")
    assert info["provider"] == "stub"
    assert isinstance(info["models"], list)
