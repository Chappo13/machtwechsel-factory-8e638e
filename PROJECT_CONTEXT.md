# YouTube Factory — генерация видео

## Проект
- Название: YouTube Factory
- Назначение: автоматизированный pipeline создания YouTube видео (DE, ES каналы)
- Статус: active (в разработке)

## Стек
- Язык: Python (backend), React (frontend)
- Фреймворки: FastAPI, React
- БД: локальные JSON/файлы (data/)
- Деплой: Railway (планируется)
- TTS: Voicer API (ElevenLabs, $50/мес)
- Стоки: Pexels API, Pixabay API
- AI: OpenRouter (сценарии), FAL API (fallback картинки)

## Структура
- Точка входа: backend/ (FastAPI), frontend/ (React)
- Ключевые файлы:
  - backend/ — API, pipeline (9 фаз)
  - frontend/ — UI управления
  - data/ — конфиги языков, голосов, тем
  - docs/STATUS.md — текущий статус
  - docs/REFERENCE_PROMPTS.md — промпты

## Pipeline (9 фаз)
1. script — генерация сценария
2. improve — улучшение
3. virality — virality filter (hook rating, pattern interrupts)
4. tts — озвучка через Voicer
5. scenes — разбивка на сцены
6. clips — подбор стоков (Pexels/Pixabay) + AI fallback
7. music — фоновая музыка
8. assembly — сборка видео
9. metadata — заголовок, описание, теги

## Архитектурные решения
- Видео 20-25 мин, стоковые клипы, музыка 10-15%
- AI-картинки только как fallback (Flux через fal.ai + Ken Burns)
- Субтитры НЕ делаем, персонаж НЕ делаем
- Бюджет: <= $100/мес на оба канала
- DE voice: Fghah4fztZORbiKfIGAs, ES: TBD

## Известные проблемы
- TTS не подключен (ждём оплату Voicer)
- Frontend ещё не создан
