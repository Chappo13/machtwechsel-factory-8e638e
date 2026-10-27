"""
Quick smoke-test for Gonka provider.
Run: GONKA_API_KEY=<your_key> python -m pytest tests/test_gonka.py -s -v

Tests:
  1. Basic call — Qwen3-235B answers a short question
  2. German script snippet — same prompt as production, Gonka vs OpenRouter
"""

import asyncio
import os
import pytest
from backend.utils.llm import call_llm, GONKA_MODELS


@pytest.mark.asyncio
async def test_gonka_basic():
    """Gonka responds at all."""
    key = os.getenv("GONKA_API_KEY", "")
    if not key:
        pytest.skip("GONKA_API_KEY not set")

    result = await call_llm(
        prompt="Say exactly: GONKA_OK",
        model=GONKA_MODELS["qwen3-235b"],
        temperature=0.0,
        max_tokens=20,
        provider="gonka",
    )
    assert "GONKA_OK" in result, f"Unexpected: {result!r}"


@pytest.mark.asyncio
async def test_gonka_german_script_snippet():
    """Gonka generates a short German documentary intro."""
    key = os.getenv("GONKA_API_KEY", "")
    if not key:
        pytest.skip("GONKA_API_KEY not set")

    result = await call_llm(
        prompt=(
            "Schreibe die ersten 3 Sätze eines deutschen Dokumentar-Voiceovers "
            "über den Wirecard-Skandal. Nur Text, keine Anmerkungen."
        ),
        model=GONKA_MODELS["qwen3-235b"],
        temperature=0.7,
        max_tokens=300,
        provider="gonka",
    )
    assert len(result) > 50, f"Too short: {result!r}"
    print(f"\n--- Gonka Qwen3-235B output ---\n{result}\n")
