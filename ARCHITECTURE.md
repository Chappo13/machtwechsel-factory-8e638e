# YouTube Factory — Architecture

> **Для агентов**: этот файл — entry point. Прочитай его прежде чем менять код.
> Он описывает зачем сделано так а не иначе и какие инварианты держать.

## Цель проекта

Автоматизированная фабрика **полуавтоматических** YouTube-видео:
агент-pipeline собирает DaVinci-проект (FCPXML 1.9 + media), кладёт в Google Drive,
шлёт владельцу ссылку в Telegram. Владелец открывает в DaVinci на маке,
добавляет motion graphics, рендерит и грузит на YouTube вручную.

Целевые рынки: DE / ES / PL (низкая конкуренция, высокий CPM €10-18).
Длительность: 20-24 мин Rise & Fall stories (финансы, бизнес-психология).

## Почему полуавтомат, а не полный

[+] Auto-upload на YouTube детектится как AI-контент, retention хуже
[+] Качество motion graphics сложно автоматизировать без потери стиля
[+] Владелец не знает DE/ES — нужен ручной контроль титров/превью
[-] Минус: владелец = bottleneck. Лимит ~3-5 видео/день вручную

## Двухпроходный pipeline (важно)

```
1. script_generation        LLM → script.txt (по теме)
2. script_improvement       3 итерации (local fix → LLM fix → polish)
3. virality_filter          hook 1-10, curiosity loops, pattern interrupts /90s
4. scene_planning           разбивка ПО ТЕКСТУ (тайминги примерные)
5. voiceover                TTS → voice.mp3 (Edge TTS или ElevenLabs)
6. ★ alignment              Deepgram STT word-level → реальные тайминги сцен
7. clip_download            стоки + FAL Flux под уточнённые тайминги
8. music                    фоновый трек по mood (12% volume в audio mix)
9. assembly                 build_fcpxml ИЛИ assemble_video (FFmpeg)
10. metadata                title/desc/tags под виральность
11. delivery                zip папки → GDrive → Telegram notify
```

**★ Alignment — критическая фаза**. Без неё клипы съезжают относительно голоса
(LLM не знает реальную скорость TTS произношения). Дважды подумай прежде чем
убирать или переставлять.

## Ключевые инварианты

[+] `task.output_mode = "fcpxml"` — полуавтомат для DaVinci (текущий боевой режим)
[+] `task.output_mode = "rendered"` — полный FFmpeg-рендер (для тестов и legacy)
[+] Voiceover duration = master timeline length (всё подстраивается под голос)
[+] Music volume = 12% (sidechain compression в DaVinci, в FCPXML — adjust-volume amount="-18.4dB")
[+] Video format: 1920x1080, 30fps, H.264 (YouTube optimal)
[+] Audio format: 48kHz stereo MP3

## TTS provider chain (fallback)

1. **Voicer API** (ElevenLabs Studio, $50/мес unlimited) — если VOICER_API_KEY есть
2. **Edge TTS** (Microsoft, free) — fallback, требует `pip install edge-tts`
3. **OpenRouter TTS** — *НЕ работает*, был preview, моделей нет в их каталоге

Voices per language: см. `backend/config/voices.yaml`.

## Структура output папки

```
data/<topic>_<lang>_<id>/
├── checkpoint.json              ← состояние pipeline (для recovery)
├── script.txt                   ← начальный сценарий
├── improved_script.txt          ← после 3 итераций улучшения
├── viral_script.txt             ← после virality filter
├── voice.mp3                    ← озвучка
├── scene_plan.json              ← разбивка по тексту (estimated)
├── scene_plan_aligned.json      ← разбивка по факту голоса (актуальная)
├── clip_map.json                ← пути и метаданные клипов
├── clips/                       ← стоки + FAL картинки
├── music.mp3                    ← фоновый трек
├── project.fcpxml               ← DaVinci timeline (если output_mode=fcpxml)
├── final_<lang>.mp4             ← рендер (если output_mode=rendered)
├── metadata_<lang>.json         ← title/desc/tags
├── QA-flags.md                  ← клипы со score <0.55 — заменить вручную
├── motion-notes.md              ← готовые тексты блоков + чеклист motion
└── open-davinci.command         ← двойной клик → DaVinci
```

## Деплой-схема

```
┌─────────────────────────┐   git push    ┌──────────────────┐
│  AIzdec workspace       │ ────────────> │  GitHub          │
│  (devshop — где пишем)  │               │  Chappo13/yt-fac │
└─────────────────────────┘               └────────┬─────────┘
                                                    │ git clone
                          ┌─────────────────────────┴──┐
                          ▼                            ▼
                ┌──────────────────┐         ┌──────────────────┐
                │  VPS prod        │         │  Mac (Sergey)    │
                │  cron daily      │         │  локальный тест  │
                │  → GDrive        │         │  → DaVinci       │
                │  → Telegram      │         │                  │
                └──────────────────┘         └──────────────────┘
```

Любой агент (Agent22, Hermes, новый) может клонировать репо и продолжить работу —
весь контекст в репо.

## Что НЕ автоматизируется (намеренно)

- Финальный монтаж в DaVinci (motion templates — твоя художественная работа)
- Превью YouTube (делается через ChatGPT-image вручную, промпт в metadata.json)
- Upload на YouTube (детектится автоматическая загрузка)
- Native validation сценария на DE/ES — gate перед TTS (план, не реализовано)

## Известные ограничения

- Voyage rate limit 3 RPM — semantic relevance scoring клипов работает медленно
- Deepgram стоит ~$0.0043/мин — на 22-мин видео ~$0.10 за alignment
- FAL Flux schnell $0.003/картинку — на 20 картинок $0.06
- Edge TTS бесплатно но качество ниже ElevenLabs
- Hermes-4 70B через Nous Portal $0.13/$0.40 за 1M — может быть основной LLM

## Стоимость одного 22-мин видео (estimate)

| Компонент             | Цена        |
|-----------------------|-------------|
| LLM (script + improve + virality + metadata) | $0.20-0.50 |
| TTS (Edge)            | $0.00       |
| TTS (ElevenLabs)      | $50/мес unlimited (амортизируется) |
| Deepgram alignment    | $0.10       |
| FAL Flux картинки     | $0.06       |
| Pexels/Pixabay стоки  | $0.00       |
| **Итого Edge**        | **~$0.40**  |
| **Итого ElevenLabs**  | **~$0.40 + $50/мес fixed** |

## Файлы критичные для понимания

- `backend/pipeline/orchestrator.py` — Pipeline + phases
- `backend/pipeline/align_scenes.py` — двухпроходка
- `backend/pipeline/fcpxml_export.py` — DaVinci output
- `backend/pipeline/tts.py` — Edge fallback dispatcher
- `backend/config/voices.yaml` — voice ID per язык
- `backend/scrapers/trending.py` — виральные темы
- `backend/pipeline/script.py` — генерация и улучшение

## История решений

- **2026-04**: пайплайн начат, DE-канал в продакшн
- **2026-05-31**: добавлен FCPXML output_mode (полуавтомат для DaVinci)
- **2026-06-01**: добавлен alignment phase (Deepgram word-level)
- **2026-06-01**: добавлен Edge TTS fallback (не зависим от ElevenLabs)
- **2026-06-01**: переход на server-side automation (cron + GDrive + Telegram)
