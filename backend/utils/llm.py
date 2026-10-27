"""
OpenRouter / Gonka LLM client.
Unified interface for all LLM calls. Supports two providers:
  - "openrouter" (default) — https://openrouter.ai
  - "gonka"               — https://gate.joingonka.ai ($0.000366/1M tok, OpenAI-compatible)
"""

import asyncio
import httpx
import logging
from backend.config import OPENROUTER_API_KEY, GONKA_API_KEY

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GONKA_URL = "https://gate.joingonka.ai/v1/chat/completions"

# Gonka model aliases (актуально 2026-07-01: qwen3-235b выбыл)
GONKA_MODELS = {
    "kimi-k2":  "moonshotai/Kimi-K2.6",     # лучшее качество, 2M ctx
    "minimax":  "MiniMaxAI/MiniMax-M2.7",   # резерв
    "glm":      "zai-org/GLM-5.2-FP8",      # резерв 2
}
# Любой из этих id в models.yaml авто-маршрутизируется на Gonka (по модели, не по
# глобальному провайдеру) — поэтому primary=Gonka, fallback=OpenRouter работает.
GONKA_MODEL_IDS = set(GONKA_MODELS.values())


def _provider_for(model: str, explicit: str = "openrouter") -> str:
    """Провайдер для КОНКРЕТНОЙ модели: Gonka-id → gonka, иначе explicit (по умолч. openrouter)."""
    if model in GONKA_MODEL_IDS:
        return "gonka"
    return explicit if explicit in ("gonka", "openrouter") else "openrouter"


async def call_llm(
    prompt: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: str = None,
    fallback_model: str = None,
    provider: str = "openrouter",
) -> str:
    """
    Call an LLM with retry + fallback.

    provider="openrouter" — default, uses OPENROUTER_API_KEY
    provider="gonka"      — uses GONKA_API_KEY, ~2800x cheaper for Qwen3/Kimi
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    models_to_try = [model]
    if fallback_model:
        models_to_try.append(fallback_model)

    last_error = None

    for model_idx, current_model in enumerate(models_to_try):
        # Провайдер резолвится ПО КАЖДОЙ модели → primary=Gonka, fallback=OpenRouter работает.
        prov = _provider_for(current_model, provider)
        api_url = GONKA_URL if prov == "gonka" else OPENROUTER_URL
        api_key = GONKA_API_KEY if prov == "gonka" else OPENROUTER_API_KEY
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": current_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # read=300: scene plan/сценарий генерятся минутами (до 32k токенов) —
        # 180с обрывался на длинных ответах
        async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=15, read=300, write=60, pool=300)) as client:
            for attempt in range(3):
                try:
                    response = await client.post(api_url, json=payload, headers=headers)

                    if response.status_code == 429:
                        wait = min(2 ** attempt * 2, 30)
                        logger.warning(f"Rate limited (429), waiting {wait}s (attempt {attempt+1}/3)")
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code == 400:
                        error_body = response.text[:500]
                        logger.error(f"LLM 400 Bad Request: model={current_model}, body={error_body}")
                        last_error = RuntimeError(f"400 from {current_model}: {error_body}")
                        break  # try fallback model

                    response.raise_for_status()

                    # Битый/не-JSON ответ при 200 — не валим, идём в ретрай/фолбэк
                    try:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                    except (ValueError, KeyError, IndexError, TypeError) as e:
                        last_error = RuntimeError(
                            f"LLM malformed response from {current_model}: {response.text[:300]}")
                        logger.error(str(last_error))
                        break  # try fallback

                    # content может прийти None/пустым (контент-фильтр, только tool_call) —
                    # НЕ возвращаем None: ретрай, затем фолбэк-модель
                    if not content or not str(content).strip():
                        last_error = RuntimeError(f"LLM empty content from {current_model}")
                        logger.warning(f"LLM empty content (attempt {attempt+1}/3, model={current_model})")
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        break  # try fallback

                    usage = data.get("usage", {})
                    cost = _estimate_cost(current_model, usage)
                    logger.info(f"LLM call: model={current_model}, tokens={usage.get('total_tokens', '?')}, cost≈${cost:.4f}")
                    return content

                except httpx.TransportError as e:
                    # Покрывает таймауты И сетевые обрывы: RemoteProtocolError
                    # («peer closed connection... incomplete chunked read»),
                    # ReadError, ConnectError. Раньше ловился только timeout —
                    # разовый обрыв соединения валил всю фазу без ретрая.
                    last_error = e
                    logger.warning(
                        f"LLM transport error (attempt {attempt+1}/3, model={current_model}): "
                        f"{type(e).__name__}: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    break  # try fallback

                except httpx.HTTPStatusError as e:
                    error_body = e.response.text[:500] if hasattr(e.response, 'text') else str(e)
                    logger.error(f"LLM HTTP {e.response.status_code}: model={current_model}, body={error_body}")
                    if e.response.status_code in (502, 503):
                        last_error = e
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                    last_error = e
                    break  # try fallback

        if model_idx < len(models_to_try) - 1:
            logger.warning(f"Falling back from {current_model} to {models_to_try[model_idx+1]}")

    raise last_error or RuntimeError("LLM call failed after all retries and fallbacks")


def _estimate_cost(model: str, usage: dict) -> float:
    """Rough cost estimate based on model and token usage."""
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    pricing = {
        # OpenRouter
        "deepseek/deepseek-chat-v3-0324": (0.15, 0.75),
        "google/gemini-2.5-flash-preview": (0.30, 2.50),
        "google/gemini-2.5-flash-preview:thinking": (0.10, 0.40),
        "google/gemini-2.5-flash": (0.10, 0.40),
        # Gonka (~$0.000366/1M all-in, effectively free)
        "qwen/qwen3-235b-a22b-instruct-2507-fp8": (0.000183, 0.000183),
        "moonshotai/kimi-k2.6":                   (0.000183, 0.000183),
        "minimaxai/minimax-m2.7":                  (0.000183, 0.000183),
    }

    rates = pricing.get(model, (1.0, 3.0))
    cost = (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000
    return cost
