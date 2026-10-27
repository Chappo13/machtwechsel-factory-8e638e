# YouTube Factory — Статус проекта

Дата: 2026-04-07
Этап: Код готов, нужен деплой на VPS/Railway

---

## Что сделано

### Бэкенд pipeline (9 фаз)
- [x] pipeline/script.py — генерация + улучшение сценария (3 итерации)
- [x] pipeline/virality.py — фильтр вирусности (hook, weak spots, pattern interrupts)
- [x] pipeline/tts.py — озвучка Voicer API (ElevenLabs безлимит)
- [x] pipeline/clips.py — scene planning + скачивание стоков
- [x] pipeline/image_gen.py — AI картинки + Ken Burns fallback (fal.ai Flux)
- [x] pipeline/music.py — фоновая музыка (Freesound.org)
- [x] pipeline/assembly.py — FFmpeg сборка (color grade, audio mix)
- [x] pipeline/metadata.py — YouTube метадата (title, description, tags)
- [x] pipeline/orchestrator.py — координация + checkpoint system

### API сервер
- [x] api/main.py — FastAPI: CORS, endpoints, WebSocket, background tasks
- [x] api/models.py — Pydantic модели (CreateVideoRequest, VideoResponse, TopicDiscoverRequest)
- [x] api/static.py — Serve React build из FastAPI (SPA catch-all)

### Веб-интерфейс (React)
- [x] frontend/src/App.jsx — 3 вкладки: Create, Queue, Library
- [x] frontend/src/App.css — Dark theme (#0a0a0f, cyan #00d4ff, glassmorphism)
- [x] frontend/src/api.js — API client + WebSocket
- [x] Vite build: 201kb bundle (63kb gzip)

### Деплой конфиги
- [x] Dockerfile — multi-stage (Node → Python + FFmpeg + yt-dlp)
- [x] railway.toml — healthcheck, restart policy
- [x] docker-compose.yml — dev: backend + frontend + shared volume

### Источники клипов
- [x] stock/multi.py — Pexels + Pixabay + Coverr

### Скрейперы
- [x] scrapers/trending.py — вирусные видео с маленьких каналов + анализ паттернов

### Конфиги
- [x] config/voices.yaml — DE/ES/EN голоса, Voicer API
- [x] config/models.yaml — LLM маршрутизация + стоимость
- [x] config/themes.yaml — темы и stock-теги
- [x] config/patterns.yaml — retention hooks + запрещённые фразы

### Промпты
- [x] prompts/script-de.md — 6-актная структура, retention techniques
- [x] prompts/script-es.md — нейтральный испанский

### Документация
- [x] docs/REFERENCE_PROMPTS.md — оригинальные промпты из референса
- [x] CLAUDE.md — Claude Code project config

---

## Что НЕ сделано

### Этап 1 — Деплой
- [ ] Railway деплой с env variables
- [ ] Тест healthcheck и WebSocket
- [ ] Проверка стоков с VPS (были проблемы)

### Этап 2 — Тестирование
- [ ] Тестовое видео на DE канал
- [ ] Тест озвучки (Voicer API)
- [ ] Тест Flux image fallback
- [ ] End-to-end pipeline run

### Этап 3 — ES канал
- [ ] Ресёрч ниши
- [ ] Подбор голоса
- [ ] Тестовое видео

### Этап 4 — После первых доходов
- [ ] YouTube auto-upload
- [ ] Dashboard аналитики
- [ ] AI-видео генерация (Kling/Runway)
- [ ] A/B тестирование заголовков

---

## Бюджет

| Статья | Стоимость |
|--------|-----------|
| TTS (Voicer/11Labs) | $50/мес (оба канала) |
| AI (OpenRouter) | $10-15/мес |
| VPS/Railway | $5-20/мес |
| Image fallback (fal.ai) | $1-5/мес |
| ИТОГО | $66-90/мес |

## Env Variables (для Railway)

```
OPENROUTER_API_KEY=...
PEXELS_API_KEY=...
PIXABAY_API_KEY=...
FALAPI=...
VOICER_API_URL=https://voicer.mat3u.com/api/v1/voice/synthesize
FREESOUND_API_KEY=... (опционально)
```
