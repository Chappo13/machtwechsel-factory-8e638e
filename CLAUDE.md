# ВАЖНО: актуальные документы (27.10.2026)

Этот файл описывает состояние апреля-мая 2026 и местами устарел. Главное сейчас:
1. `HANDOFF.md`: что в репозитории, как запускать, где что сломано.
2. `PLAN-CHEAP-FACTORY.md`: что и в каком порядке менять, чтобы завод стал дешёвым и делал хорошие ролики. При расхождении с этим файлом прав план.
3. `docs/GAP-ANALYSIS.md` и `docs/tainy-essence/`: обоснования, цифры, как устроен Tainy.

Устарело в этом файле, не следуй:
- «LLM только через backend/utils/llm.py (OpenRouter)» и озвучка Voicer/ElevenLabs по умолчанию: по плану LLM идёт по подписке Claude владельца, озвучка по умолчанию дешёвая (Edge TTS), платное включается явным параметром.
- Картинки Flux как запасной путь и режим stick_figure: для канала Machtwechsel убираются.
- Веб-API и React: на сервере не запускать, управление через `factory.py` и файлы задач.
- Тяжёлое (Chromium, Remotion, перекодирование видео) на сервере не запускать, только на Mac; стадии на сервере идут отдельной службой с лимитом памяти, не из чата.
- Не запускать `autorun.py` и тесты, которые ходят во внешние платные API.
- Ключи не печатать и не писать в файлы; не публиковать видео без согласия владельца.

---

# YouTube Factory

Automated YouTube video generation platform for multilingual faceless channels (DE/ES).

## Overview

Pipeline: script → improve → virality filter → TTS → stock clips → music → FFmpeg assembly → metadata

## Tech Stack

- Python 3.11+, FastAPI (backend)
- FFmpeg (video assembly)
- Voicer API / ElevenLabs v3 (TTS, $50/mo unlimited)
- OpenRouter (LLM — Gemini/GPT)
- Pexels + Pixabay + Coverr (stock footage, free)
- fal.ai Flux (AI image fallback)
- React (frontend, coming)

## Architecture

```
backend/
  pipeline/       # 9-phase video generation
    orchestrator.py  # Main coordinator + checkpoint system
    script.py        # Script gen + 3-iteration improvement
    virality.py      # Hook rating, weak spots, pattern interrupts /90s
    tts.py           # Voicer API (ElevenLabs), chunked synthesis
    clips.py         # Scene planning + multi-source download
    image_gen.py     # AI image fallback (Flux + Ken Burns)
    music.py         # Freesound.org, mood-based
    assembly.py      # FFmpeg: normalize, color grade, concat, audio mix
    metadata.py      # YouTube SEO (title, desc, tags)
  scrapers/
    trending.py      # Find viral videos from small channels, analyze patterns
  stock/
    multi.py         # Pexels + Pixabay + Coverr unified client
  config/            # YAML configs (voices, models, themes, patterns)
  prompts/           # LLM prompt templates per language (DE/ES)
  api/               # FastAPI server (TODO)
  utils/
    llm.py           # OpenRouter client with cost tracking
frontend/            # React web UI (TODO)
docs/
  STATUS.md          # Current progress and roadmap
  REFERENCE_PROMPTS.md  # Original prompts from reference creator
```

## Commands

- Run backend: `cd backend && uvicorn api.main:app --reload`
- Run tests: `pytest tests/`

## Conventions

- Language: Python 3.11+ with type hints
- Async: All pipeline phases are async (await)
- Config: YAML files in backend/config/, loaded via backend/config/__init__.py
- LLM calls: Always through backend/utils/llm.py (OpenRouter)
- Environment: API keys via .env (see .env.example)
- Git commits: `[agent] type: description`
- Video output: 1920x1080, 30fps, H.264, CRF 20

## Key Decisions

- NO subtitles (not needed for documentary format)
- NO animated character (cost, added later)
- NO AI video generation yet (expensive, after revenue)
- Stock footage + AI image fallback (Flux $0.01/image + Ken Burns)
- Virality filter as SEPARATE phase (not merged into improvement)
- Budget target: ≤$100/month for both channels
- Video length: 20-25 minutes each
- Music: 10-15% volume, mood-matched

## Channels

- DE: Finance/Business — Rise & Fall stories (CPM €12-18)
- ES: TBD — research phase (likely Dark Psychology or Business)

## Current Status

See docs/STATUS.md for full roadmap. Next: FastAPI server + React frontend.
