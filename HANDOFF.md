# HANDOFF: YouTube Factory (канал Machtwechsel, DE)

Дата передачи: 22.10.2026. Оригинал (приватный, тебе недоступен): https://github.com/Chappo13/youtube-factory. Ты работаешь в этой публичной копии (снимок ветки integrate на 27.10.2026, без истории); ссылки на оригинал ниже и в документах не используй, склонировать его не получится.
Канал: https://www.youtube.com/channel/UCB0e_XDdaXb3SHdA4-bieBw (немецкий, финансы и крахи компаний).

> **Дополнение 27.10.2026.** Дальше завод дорабатывается по плану `PLAN-CHEAP-FACTORY.md` (что оставить, заменить, добавить, убрать, роли и порядок работ, критерии готовности). Обоснования и цифры: `docs/GAP-ANALYSIS.md`. Как устроен Tainy, завод владельца, который делает хорошие ролики: `docs/tainy-essence/`. Сначала прочитай этот файл, потом план. Сначала собери тестовый ролик на 3 минуты без платных вызовов (фаза 1 плана), потом полный.

## 0. Главное за минуту

- Самая свежая рабочая ветка: `integrate` (коммит от 20.07.2026). Работай от неё. `master` отстаёт на один коммит (только untrack mp3).
- Другие ветки: `master` (01.07), `feat/fcpxml-davinci-export` (04.06, первая версия экспорта в DaVinci), `v5` (03.06), `agent/ui-v2-redesign` (22.06).
- Завод полуавтомат: сервер собирает папку с проектом DaVinci и ассетами, zip забирает человек, монтирует на MacBook, рендерит и грузит на YouTube вручную. Кода автозагрузки на YouTube в репозитории нет.
- **В `channels.yaml` на `integrate` профиль `de` теперь не Machtwechsel, а "Nina" (curiosity, стикмены, id `UCVZZnW0SO_AAWqQCfTbgRPg`).** Профиль Machtwechsel (финансы, `niche: finance`, 22 мин, третье лицо) удалён коммитом `da5eb5c`. Чтобы запускать завод для Machtwechsel, восстанови его: `git show b566bf4:backend/config/channels.yaml` (там блок `de` с id `UCB0e_XDdaXb3SHdA4-bieBw`). Не перезаписывай им Nina, заведи отдельный ключ или другой язык-слот (одно значение `lang` = один канал).
- Рабочая директория на старом сервере была `/home/client/projects/youtube-factory-v5`. На сервере Сергея копия лежит в `~/archive/projects/youtube-factory-v5` (без `.git`, равна `integrate`, кроме двух файлов из `data/output`, они теперь в `docs/legacy-de/`).

## 1. Конвейер

```
тема → сценарий → озвучка → картинки/видео → превью → сборка → zip → рендер на Mac → YouTube
```

| # | Шаг | Что происходит | Код |
|---|-----|----------------|-----|
| 1 | Тема | Discovery трендов по малым каналам, дедуп с уже опубликованным на канале (YouTube Data API, кэш `data/channel_videos_{lang}.json`, 12 ч), очередь `data/queue.json` | `backend/scrapers/trending.py`, `autorun.py --discover` |
| 2 | Сценарий | Генерация, 3 итерации улучшения, humanize, judge, фильтр виральности. Гейт: после сценария пауза (`script_ready`), человек одобряет | `pipeline/script.py`, `virality.py`, `prompts/script-*.md` |
| 3 | Озвучка | TTS кусками, порядок провайдеров Voicer → fal (ElevenLabs v3) → Edge TTS | `pipeline/tts.py`, `config/voices.yaml` |
| 4 | Выравнивание | Deepgram word-level, сцены пересчитываются под реальный голос. Не убирать, иначе клипы уезжают от голоса | `pipeline/align_scenes.py` |
| 5 | Картинки/видео | Режим `stick_figure`: fal Seedream v4 (edit по `reference_stick.png`). Режим стоков: Pexels/Pixabay (+Coverr), Flux как запасной. Инфографика (счётчики, графики, карты) рендерится Remotion | `pipeline/stick_figure.py`, `clips.py`, `image_gen.py`, `remotion_render.py`, `remotion/` |
| 6 | Музыка | Freesound по настроению или своя библиотека, громкость около 12-22% | `pipeline/music.py`, `music_select.py` |
| 7 | Сборка | `output_mode="fcpxml"`: проект DaVinci (FCPXML 1.9, относительные пути) плюс `QA-flags.md`, `motion-notes.md`, `open-davinci.command`. `output_mode="rendered"`: готовый mp4 через FFmpeg (для тестов) | `pipeline/fcpxml_export.py`, `assembly.py` |
| 8 | Метаданные и превью | 3 заголовка, описание, теги, закреп-коммент, моменты для Shorts, промпты превью. Файл `PUBLISH_{lang}.md` для копипаста | `pipeline/metadata.py` |
| 9 | Доставка | Zip папки (медиа без сжатия), загрузка в Google Drive, уведомление в Telegram. Если Drive не настроен, zip остаётся на сервере и качается кнопкой на сайте. После доставки сырые медиа в workspace удаляются | `pipeline/delivery.py`, `gdrive.py`, `gdrive_auth.py` |
| 10 | Рендер на Mac | См. раздел 4 | вручную |
| 11 | YouTube | Загрузка вручную. Превью делает человек сам по промптам из `PUBLISH_*.md` (автопревью выключено в коде, `if False`) | вручную |

Фазы идут через чекпоинты (`checkpoint.json` в папке задачи), упавшая задача продолжается с места падения.

## 2. Как запускать

### Вариант A: веб-сервис (так работал прод на Railway)
```bash
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```
Основные ручки (`/api/v1`): `POST /scripts` (сценарий с гейтом), `POST /videos/{id}/approve` (клонирует черновик в новую задачу и собирает; нажимать один раз, иначе двойной расход), `POST /videos` (сразу всё), `/videos/{id}/retry`, `/rebuild`, `/translate`, `GET /videos/{id}/download`, `POST /channels/{lang}/discover`, `GET /health`. Прогресс по WebSocket `/ws/{task_id}`. Сайт под паролем `SITE_PASSWORD`.
Docker: `Dockerfile` (Node → Python + FFmpeg + yt-dlp + Chromium для Remotion), `railway.toml`, том `data` в `/app/data`.

### Вариант B: командная строка
```bash
python3 autorun.py --topic "Wie Wirecard Deutschland täuschte" --lang de --duration 22
python3 autorun.py --discover        # только поиск новых тем в data/queue.json
python3 autorun.py                   # взять первую тему со статусом approved
```
Статусы очереди: `pending_approval` → `approved` → `running` → `done` / `failed`. Автозапуск: `deploy/youtube-factory.service` + `.timer` или cron (`deploy/crontab.example`), установка на VPS `deploy/install-on-vps.sh`. Подробности: `DEPLOYMENT.md`.

### Вариант C: на Mac двойным кликом
`Setup_Mac.command` (один раз: brew, ffmpeg, venv, шаблон `.env`), `Make_Video.command` (тема, язык, длина правятся в файле), `Realign_Voice.command` (пересчёт сцен после замены `voice.mp3`).

## 3. Внешние сервисы, модели и переменные окружения

Только имена. Значения лежат в хранилище ключей владельца (настройки агента), в репозитории их нет.

| Назначение | Сервис / модель | Переменные |
|---|---|---|
| LLM (сценарий, улучшение, judge, сцены, перевод, метаданные) | Gonka gateway (`gate.joingonka.ai`), модели Kimi-K2.6 (основная) и MiniMax-M2.7 (запасная); OpenRouter как запасной путь (Gemini и др.) | `GONKA_API_KEY`, `OPENROUTER_API_KEY` |
| TTS | Voicer (ElevenLabs v3), далее fal `fal-ai/elevenlabs/tts/eleven-v3`, далее Edge TTS | `VOICER_API_KEY`, `VOICER_ENDPOINT`, `FALAPI`, `EDGE_VOICE_DE/ES/EN/PL/VI`, `ALLOW_EDGE_FALLBACK` |
| Выравнивание голоса | Deepgram | `DEEPGRAM_API_KEY` |
| Картинки | fal: `bytedance/seedream/v4/edit`, `.../text-to-image`, `flux/schnell`, `flux-pro/v1.1` | `FALAPI` |
| Стоки | Pexels, Pixabay, Coverr | `PEXELS_API_KEY`, `PIXABAY_API_KEY` |
| Музыка | Freesound | `FREESOUND_API_KEY` |
| Дедуп тем по каналу | YouTube Data API | `YOUTUBE_DATA_API` (или `YOUTUBE_API_KEY`) |
| Эмбеддинги (релевантность клипов) | Voyage | `VOYAGE_API_KEY` |
| Доставка | Google Drive (OAuth), Telegram-бот | `GDRIVE_FOLDER_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `OWNER_CHAT_ID` (или `OWNER_ID`) |
| Сервер | пароль сайта, Remotion | `SITE_PASSWORD`, `REMOTION_CHROME_EXECUTABLE`, `REMOTION_DIR`, `PORT` |

Google Drive один раз авторизуется командой `python3 -m backend.pipeline.gdrive_auth`; токен сохраняется в `.gdrive_token.json` (в zip не попадает и в git игнорируется).

## 4. Рендер на MacBook

Что в zip (папка `data/<тема>_<язык>_<id>/`): `project.fcpxml` (таймлайн), `voice.mp3`, `music.mp3`, `clips/` (стоки, картинки, ролики Remotion), `QA-flags.md` (клипы с низкой релевантностью, заменить вручную), `motion-notes.md` (тексты блоков и чеклист графики), `metadata_<lang>.json`, `PUBLISH_<lang>.md`, `scene_plan*.json`, `open-davinci.command`.

Нужно на Mac: DaVinci Resolve (импорт FCPXML 1.9), собственные шаблоны motion graphics / Fusion-пресеты владельца (в репозитории их нет), для запуска скриптов завода локально: Homebrew, ffmpeg, Python 3.11, `pip install -r requirements.txt edge-tts python-dotenv`.

Порядок: распаковать zip, двойной клик `open-davinci.command`, заменить клипы из `QA-flags.md`, добавить motion по `motion-notes.md`, посмотреть, отрендерить 1920x1080 / 30 fps / H.264, загрузить. Если голос заменён (например переозвучен в ElevenLabs), запусти `Realign_Voice.command` и пересобери FCPXML.

## 5. Загрузка на YouTube

Полностью вручную через YouTube Studio. Заголовок, описание, теги, закреп-комментарий и моменты для Shorts берутся из `PUBLISH_<lang>.md`. Превью делается вручную (промпты в метаданных). Автозагрузка сознательно не делалась (риск детекта как AI-контента и ручной контроль немецкого). Кода под YouTube upload API и OAuth-токенов канала в репозитории нет. Для YouTube используется только Data API по ключу (чтение списка роликов), а не yt-dlp: на серверах он ловит "Sign in to confirm you're not a bot".

## 6. Что вышло и что в работе

Данные на 21.10.2026 (канал @Machtwechselde, 14 роликов, 3 518 просмотров всего):
- Волна 22.02: «VW: Die 25-Milliarden-Euro-Lüge» (1 500), «Neuseeland: Der 50.000-Personen-Exodus» (1 200), остальные 15-43 просмотров. Список из кэша дедупа на 16.06: Siemens-Schmiergeld, VW-Dieselskandal, "Ich verstehe sie. Warum immer mehr Deutsche einfach gehen", El Fasher (69.000 Tote), Venezuela (100 Mrd), Carnegie (480 Mio), J.P. Morgan, Neuseeland, VW 25 Mrd.
- Волна 22.06: VW-Diesel (288), Siemens (134).
- Стикмены 22.07 на немецком не зашли (0-33). Ролик про курение: на испанском 1 400, на немецком 33.
- Полный список 14 названий возьми из YouTube Studio или `yt-dlp --flat-playlist`; в репозитории хранится только кэш на 9 названий.

Не опубликовано / не доведено:
- Тестовая тема `Wie Wirecard Deutschland täuschte` (используется в примерах и `Make_Video.command`), выпуск не подтверждён.
- «Massenflucht der Fachkräfte» (v4.1): метаданные в `docs/legacy-de/MASSENFLUCHT_METADATA.txt`. Выходил ли ролик под этим названием, не проверено: возможно, это опубликованный «Ich verstehe sie…».
- Идеи сиквелов и референсы (Wirecard, CumEx, Deutsche Bank/Lehman, Signa, P&R, Wirtschaftskrise): `docs/legacy-de/DE_CHANNELS_AND_REFERENCES.md`.
- `data/queue.json` в репозитории и в архиве отсутствует: актуальная очередь жила на томе Railway. Если нужна, её надо достать из прода.

## 7. Сломано, устарело, делалось вручную

- Профиль Machtwechsel удалён из `channels.yaml` (см. раздел 0). Стикмены на DE не работают, финансовые расследования работали лучше.
- Нет автозагрузки на YouTube, нет автопревью (выключено), финальный монтаж и мотион только вручную в DaVinci.
- Python-зависимости в `requirements.txt` покрывают импорты кода, но системные пакеты (ffmpeg, Chromium, Node, yt-dlp) ставит только `Dockerfile`. Для remotion нет `package-lock` (образ невоспроизводим).
- Известные проблемы из `docs/e2e-issues.md` и `docs/AUDIT.md`: сценарий выходит короче целевых 22 минут (virality/improve укорачивают), клипы в FCPXML кладутся встык, из-за чего видеоряд может уезжать от голоса к концу; cut_points не заполняются; шрифт Inter не установлен в образ; квота YouTube API около 1020 единиц на discover; прогресс считается по 9 фазам при 11 реальных.
- Voicer нестабилен (воркер лежал 13-23.06), поэтому в коде есть fal-фолбэк. Voyage даёт 3 запроса в минуту.
- yt-dlp блокируется на датацентровых IP.
- Тесты: `tests/test_pipeline_phases.py` и `test_gonka.py` ходят во внешние API и тратят деньги, запускай осознанно.
- Старые доки (`STATUS.md`, `README.md`, `CLAUDE.md`) описывают состояние апреля-мая (OpenRouter, только стоки), актуальнее `ARCHITECTURE.md`, `docs/DAVINCI-WORKFLOW.md` и этот файл. Напоминание про `ARCHITECTURE.md`: упоминает Hermes/Nous как возможный LLM, фактически используется Gonka.
- Сеть каналов Nina (de), El Porqué (es), Homo Raconte (fr), Cave to Couch (en) и перевод одного сценария на 4 языка с переиспользованием картинок появились 23.06; Machtwechsel туда не входит.
