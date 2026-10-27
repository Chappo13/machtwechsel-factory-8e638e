# Stick-Figure Workflow — анализ для YouTube Factory V5

Источник: видео @zapiwala ai «Claude Code (Free Plan) + YouTube = $77,000/Month»
URL: https://www.youtube.com/watch?v=WVT2FCjhDDY
Дата разбора: 2026-06-13

> Документ — конкретно про **видеоряд** (где у V5 сейчас узкое место). TTS, скрипт, тайтлы — пропускаю, у нас уже есть.

---

## Главный вопрос: статика или анимация?

**Ответ: чистая статика. Никакой анимации.**

Дословные цитаты из транскрипта:

> «No fancy animation, no 3D characters, no cinematic visuals, **not even video clips**, just **still images** of stick figures one after another stitched together into a full video.»

> «Static images, stick figures with 7.5 million views.»

> «That Stickman channel crossed 7.5 million views with **still images**.»

В Google Flow он выбирает **image mode**, не video mode. Каждая «сцена» — это ОДНА статичная PNG, которая держится N секунд (от паузы до паузы в озвучке).

**Иллюзия движения создаётся ТРЕМЯ вещами**:
1. Частая смена картинок (100+ сцен на 5-15-минутное видео → новая сцена каждые 3-8 секунд).
2. Ритм нарезки от пауз в voiceover, не равномерный.
3. Простота стика — глаз не успевает «заскучать» от статики, потому что между сценами проходит ≤8 секунд.

**Никакого Pika/Runway/Kling/SVD оживления НЕТ.** Это критично: ты беспокоился что animation дорогая — её нет в этой схеме вообще.

---

## Что именно генерируют (и чем заменить)

### Что у него (видеоряд)

| Компонент           | Инструмент               | Цена                        | API? |
|---------------------|--------------------------|----------------------------|------|
| Image generation    | **Google Flow** + Nano Banana 2 | бесплатно (с rate limits)   | НЕТ |
| Bulk-генерация UI   | Zappy Flow Chrome extension (его самопальный) | бесплатно             | НЕТ — скрейпер UI |
| Pause-detection     | faziscribe.ai            | 10 мин/free аккаунт         | НЕТ |
| Монтаж              | любой видеоредактор вручную | бесплатно                | — |

**Проблемы его схемы для нас**:
- Google Flow — нет API. Чтобы автоматизировать, надо либо его расширение, либо свой Playwright-скрипт (нестабильно, банят).
- faziscribe — на 100-сценное видео уйдёт регистрация ≥3-4 новых аккаунтов. На постоянку не подходит.
- Ручной монтаж 100+ сцен — это часы работы, у нас YouTube Factory должен быть автоматический.

### Что берём вместо (для V5)

| Компонент           | Чем заменить            | Цена                        | API |
|---------------------|-------------------------|-----------------------------|-----|
| Image generation    | **FAL Flux Schnell** или **FAL Flux Dev** | $0.003/img (Schnell), $0.025/img (Dev) | ДА |
| Альтернатива image  | Replicate SDXL / Lightning | $0.003-0.005/img         | ДА |
| Альтернатива image  | OpenAI gpt-image-1 / Gemini image  | дороже, ~$0.04/img | ДА |
| Pause-detection     | **Whisper-large-v3** локально или **Deepgram** word-timestamps | локально 0 / Deepgram уже оплачен | ДА |
| Bulk-генерация      | свой Node/Python скрипт через FAL API | included         | — |
| Монтаж              | **ffmpeg** скрипт (у V5 уже Remotion стоит — можно через него) | бесплатно | — |

### Цена видеоряда для V5 stick-figure варианта

Пример: 22-минутное видео, **100 сцен**.

| Статья                  | FAL Flux Schnell | FAL Flux Dev    |
|-------------------------|------------------|-----------------|
| 100 картинок            | $0.30            | $2.50           |
| Whisper (локально)      | $0                | $0              |
| ffmpeg сборка           | $0                | $0              |
| **Итого видеоряд**      | **$0.30**         | **$2.50**       |

Для сравнения — текущий V5 на Pexels: ~$0 видеоряд (но контроля над контентом нет, лотерея). Стик-фигуры дороже Pexels на $0.30-2.50, но контент-завод управляемый.

Дев vs Schnell: Schnell — 4 шага, быстрее, картинка проще. Для стик-фигур этого хватает с запасом (там нечего детализировать). Берём Schnell.

---

## Стилевой промпт для консистентного стика

Чтобы все 100 сцен были в едином стиле — фиксируем стиль-префикс и меняем только сцену.

**Базовый промпт** (приставляется к каждой сцене):

```
hand-drawn black stick figure on pure white background, minimalist doodle,
single line art, ultra simple, no color, no shading, no gradients,
centered composition, marker pen style
```

**Пример конкретной сцены**:

```
<base prompt>, stick figure sitting at a desk, head in hands, laptop in front,
clock showing 2:00 AM on the wall behind
```

Claude (через Anthropic API) генерирует только описание сцены — стиль-префикс приклеивается кодом. Это даёт ~100% консистентность стиля.

---

## Pause-driven scene cutting (главный технический инсайт)

Алгоритм (как у автора, переведённый в код):

1. Озвучиваем скрипт → mp3 (нам берёт твой голос).
2. Прогоняем mp3 через Whisper-large-v3 с `word_timestamps=True` → JSON: `[{"word": "...", "start": 0.12, "end": 0.34}, ...]`.
3. Идём по списку, считаем разрыв `next.start - current.end`. Если >0.3-0.5 сек — это пауза, граница сцены.
4. Группируем слова в реплики между паузами → это список «сцен» с их `(start_ms, end_ms, text)`.
5. По тексту реплики Claude генерит описание визуала + стиль-префикс → промпт.
6. FAL Flux Schnell генерит PNG на каждый промпт.
7. ffmpeg склейка: каждая PNG показывается с `start_ms` до `end_ms` поверх voiceover.

**Порог паузы (0.3s vs 0.5s vs 0.7s)** — это калибровка под голос. Для нарративного спокойного голоса (как Raunak у автора, или твой) — 0.3-0.4с даёт правильный ритм. Для быстрого голоса — 0.5-0.7с, иначе нарезка будет дёргаться.

---

## Применение к существующему V5

В V5 уже есть:
- backend/ — pipeline кода
- remotion/ — видеомонтажный движок (даже лучше ffmpeg для шаблонов)
- frontend/ — UI

**Что добавить** (минимальная инвазия, не ломая текущий Pexels-режим):

1. Новый `mode` в конфиге видео: `pexels` (текущий) | `stick_figure`.
2. Если `stick_figure`:
   - На этапе TTS не дёргаем Pexels.
   - Добавляем шаг `pause_detect.py` (Whisper → pauses → scenes).
   - Шаг `prompt_gen.py` (Claude → image prompts со стиль-префиксом).
   - Шаг `images_gen.py` (FAL Flux Schnell → 100 PNG).
   - Remotion-шаблон `StickFigure.tsx`: PNG + voiceover + кросс-фейды 0.1s между сценами.
3. UI: галочка «Stick-figure mode» в форме создания видео.

Объём работы: 1-2 вечера на MVP, при условии что FAL и Whisper уже подключены (Whisper стоит проверить — Deepgram точно есть).

---

## Полный workflow автора (для справки, чтобы помнить контекст)

(Жирным — то, что критично; курсивом — пропускаем или заменяем у себя)

1. Один промпт в Claude AI free → 5 viral topic ideas + полный скрипт + TXT-файл.
2. *ElevenLabs free, голос Raunak → mp3.* (У тебя свой голос.)
3. *faziscribe.ai → таймштампы пауз.* (Заменяем на Whisper.)
4. Тот же чат Claude → text-to-image prompts по каждому таймштампу (батчами, командой «next»).
5. *flow.google + Nano Banana 2 → ручная генерация по 1 промпту.* (Заменяем на FAL API.)
6. *Zappy Flow Chrome extension — bulk-генерация в фоне.* (Не нужно, у нас прямой API.)
7. **Ручной монтаж** — voiceover на timeline, картинки по порядку, нарезка по timestamps из имени файла. (Заменяем на ffmpeg/Remotion.)
8. Claude → metadata (title/desc/tags) + 5 thumbnail-промптов → bulk через Zappy. (Metadata оставляем, thumbnails — FAL.)
9. Upload на YouTube.

---

## Что нужно проверить перед стартом MVP

- [ ] Подключен ли в V5 уже FAL API key? Если да — какие модели лицензированы.
- [ ] Подключен ли Whisper (локально или через FAL/Deepgram API)?
- [ ] Каков формат вывода TTS в V5 — даёт ли он чистый mp3/wav, или уже склеенный с видео?
- [ ] Remotion vs ffmpeg — какой пайплайн быстрее для 100+ сцен с разной длительностью.
- [ ] Тест 3-минутного ролика на стике перед полным каналом.

---

## Ссылки

- Транскрипт исходного видео: `~/workspace/knowledge/youtube-transcript-extraction.md` (как доставать через Apify)
- Общий разбор: `~/workspace/memory/2026-06-13.md`
- FAL Flux: https://fal.ai/models/fal-ai/flux/schnell
- Whisper word timestamps: openai-whisper Python пакет, флаг `word_timestamps=True`
