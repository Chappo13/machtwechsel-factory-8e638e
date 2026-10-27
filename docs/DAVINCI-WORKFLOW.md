# DaVinci semi-auto workflow

Pipeline собирает не финальное видео, а DaVinci-проект (FCPXML 1.9 + media)
с уже разложенными клипами, голосом и музыкой. Сергей открывает в DaVinci,
добавляет motion graphics из своих шаблонов, рендерит и грузит сам.

## Pipeline (двухпроходный)

```
1. script_generation       LLM → script.txt
2. script_improvement      3 итерации улучшения
3. virality_filter         hook rating, curiosity loops, pattern interrupts
4. scene_planning          разбивка на сцены ПО ТЕКСТУ (тайминги примерные)
5. voiceover               TTS → voice.mp3
6. ★ alignment             Deepgram STT → word-level timestamps →
                            scene_plan пересчитан под РЕАЛЬНЫЙ голос
7. clip_download           стоки/FAL под уточнённые тайминги
8. music                   фоновый трек по mood
9. assembly (fcpxml)       project.fcpxml + QA-flags.md + motion-notes.md
10. metadata               title/desc/tags + промпт превью
```

## Запуск (на маке Сергея)

### Установка
```bash
git clone https://github.com/Chappo13/youtube-factory.git
cd youtube-factory
git checkout feat/fcpxml-davinci-export
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Edge TTS как fallback если нет ElevenLabs
pip install edge-tts
brew install ffmpeg  # если ещё нет
```

### Env
```bash
cat > .env <<EOF
OPENROUTER_API_KEY=...     # для LLM (script, virality, metadata)
DEEPGRAM_API_KEY=...       # для alignment phase (word-level STT)
FALAPI=...                 # FAL Flux для генерации изображений (B-roll fallback)
PEXELS_API_KEY=...
PIXABAY_API_KEY=...
# VOICER_API_KEY=...       # ОПЦИОНАЛЬНО — если нет, Edge TTS используется как fallback
# GDRIVE_FOLDER_ID=...     # опциональная выгрузка
EOF
```

### Прогон задачи
```python
import asyncio
from backend.pipeline.orchestrator import VideoTask, Pipeline

task = VideoTask(
    topic="Wie Wirecard Deutschland täuschte",
    lang="de",
    duration_minutes=22,
    output_mode="fcpxml",   # ← полуавтомат для DaVinci
)

pipeline = Pipeline()
asyncio.run(pipeline.run(task))
print(f"Output: {task.workspace}")
```

## Что получишь на выходе

```
data/<topic>_de_<id>/
  project.fcpxml             ← DaVinci timeline
  voice.mp3                  ← Edge TTS (или ElevenLabs если ключ есть)
  music.mp3
  clips/
    01.mp4
    02.mp4
    ...
  QA-flags.md                ← клипы с relevance < 0.55 — заменить вручную
  motion-notes.md            ← готовые тексты блоков + чеклист motion
  metadata_de.json           ← топ-3 title/desc/tags
  open-davinci.command       ← двойной клик → DaVinci открывает project.fcpxml
  checkpoint.json
  scene_plan.json + scene_plan_aligned.json
```

## Финальный шаг (твой)

1. Двойной клик `open-davinci.command` → DaVinci подгружает timeline
2. Открыть `QA-flags.md` → заменить плохие клипы вручную
3. Открыть `motion-notes.md` → добавить motion templates из своих Fusion-пресетов
4. Просмотр → рендер → загрузка на YouTube

## Повторное выравнивание после правки голоса

Если ты заменил `voice.mp3` (например, переозвучил в ElevenLabs UI) —
прогон отдельно alignment'а:

```python
from backend.pipeline.align_scenes import realign_scene_plan
from pathlib import Path
import asyncio

asyncio.run(realign_scene_plan(
    voice_path=Path("data/<topic>/voice.mp3"),
    scene_plan_path=Path("data/<topic>/scene_plan.json"),
    lang="de",
))
```

Затем перегенерация FCPXML с новыми таймингами:

```python
from backend.pipeline.fcpxml_export import build_fcpxml
# build_fcpxml(workspace=..., clips=clips_from_aligned_plan, voiceover_path=..., music_path=...)
```

## TTS Provider

Текущая логика выбора в `_synthesize_chunk_dispatch`:

1. Если `VOICER_API_KEY` задан + voice_id в config — используется Voicer (ElevenLabs)
2. Иначе — Edge TTS (бесплатно, требует `pip install edge-tts`)

Edge voice mapping в `backend/config/voices.yaml`:
- de: `de-DE-KatjaNeural`
- es: `es-ES-ElviraNeural`
- en: `en-US-AriaNeural`

Можно переопределить через env:
```bash
EDGE_VOICE_DE=de-DE-ConradNeural
EDGE_VOICE_ES=es-ES-AlvaroNeural
```

Список всех Edge голосов: `edge-tts --list-voices`
