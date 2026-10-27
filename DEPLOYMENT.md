# Deployment — production runbook

Краткое руководство по развёртыванию YouTube Factory как daily content-завод
на VPS с авто-доставкой готовых zip-папок владельцу через Telegram + GDrive.

## Архитектура production

```
Cron @ 04:00 UTC
    │
    ▼
autorun.py reads queue.json
    │
    ▼
Pipeline (10 phases: script → ... → fcpxml → zip → GDrive → Telegram notify)
    │
    ▼
Owner получает в Telegram сообщение со ссылкой на zip в GDrive
    │
    ▼
Скачивает zip → распаковывает → open-davinci.command → DaVinci
```

## Где запускать

- **Любой Ubuntu/Debian VPS** с 2GB RAM, 50GB disk, Python 3.11+
- Рекомендую отдельный $12 DO Basic droplet (изоляция от agent-vps)
- Альтернатива: можно подселить к agent-vps (только в FCPXML mode — без FFmpeg рендера, лёгкая нагрузка)

## Установка (на чистом VPS)

```bash
# 1. SSH на VPS
ssh ubuntu@<vps-ip>

# 2. Скачать install скрипт
curl -fsSL https://raw.githubusercontent.com/Chappo13/youtube-factory/feat/fcpxml-davinci-export/deploy/install-on-vps.sh -o install.sh
bash install.sh

# 3. Заполнить .env (значения из AIzdec /settings → 🔑)
cd ~/youtube-factory
nano .env
```

### Что должно быть в .env (минимум)

```
OPENROUTER_API_KEY=...       # script, virality, scenes, metadata
DEEPGRAM_API_KEY=...          # alignment phase
FALAPI=...                    # FAL Flux для B-roll генерации
PEXELS_API_KEY=...
PIXABAY_API_KEY=...

# Для Telegram-уведомлений:
TELEGRAM_BOT_TOKEN=...        # бот, который шлёт владельцу
OWNER_CHAT_ID=...             # твой chat_id (узнать через @userinfobot)

# Для GDrive выгрузки (опционально):
GDRIVE_FOLDER_ID=...          # ID папки куда лить zip'ы
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

GDrive нужен один раз пройти OAuth:
```bash
cd ~/youtube-factory && source .venv/bin/activate
python3 -m backend.pipeline.gdrive_auth
# Открой ссылку в браузере → авторизуй → код вставь обратно в терминал
```

## Тестовый прогон

Короткое видео 3 минуты для проверки что pipeline работает end-to-end:
```bash
.venv/bin/python3 autorun.py --topic "Wie Wirecard Deutschland täuschte" --lang de --duration 3
```

Если упало — смотри `logs/autorun.log` и `logs/autorun.err`.

## Авто-запуск (cron или systemd)

### Вариант A — cron

```bash
crontab -e
```

Добавь:
```
# Ежедневный прогон в 04:00 UTC
0 4 * * * cd ~/youtube-factory && .venv/bin/python3 autorun.py >> logs/autorun.log 2>&1

# Discovery новых тем — каждый понедельник в 03:00
0 3 * * 1 cd ~/youtube-factory && .venv/bin/python3 autorun.py --discover >> logs/autorun.log 2>&1
```

### Вариант B — systemd (предпочтительно)

```bash
sudo cp deploy/youtube-factory.service /etc/systemd/system/
sudo cp deploy/youtube-factory.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now youtube-factory.timer
sudo systemctl list-timers youtube-factory.timer
```

## Очередь тем (queue.json)

`data/queue.json` — приоритетный список тем:
```json
[
  {
    "topic": "Wie Wirecard Deutschland täuschte",
    "lang": "de",
    "duration_minutes": 22,
    "status": "approved"
  },
  {
    "topic": "Der Aufstieg und Fall von Nokia",
    "lang": "de",
    "duration_minutes": 22,
    "status": "pending_approval"
  }
]
```

Статусы:
- `approved` — готово к прогону, autorun возьмёт первой
- `pending_approval` — discovery нашёл, владелец должен одобрить вручную (поменять статус на `approved`)
- `running` — в работе сейчас (autorun сам ставит)
- `done` — готово, есть `result.gdrive_url`
- `failed` — упало, см. `error` поле

## Что владелец получает

Telegram-сообщение от бота:
```
✓ Новое видео готово

Тема: Wie Wirecard Deutschland täuschte
Язык: DE · Длительность: ~22 мин
QA-флагов: 2 (клипы для замены)

📦 Скачать zip с GDrive

Топ-3 названия:
  1. Wirecards $2B Betrug — Wie 25 Jahre Lügen entlarvt wurden
  2. Wie Wirecard Deutschland täuschte (DAX-Skandal erklärt)
  3. Vom DAX zur Insolvenz — Wirecards spektakulärer Crash

Открой open-davinci.command в скачанной папке → DaVinci загрузит timeline.
```

Внутри zip:
- `project.fcpxml` — открыть в DaVinci
- `voice.mp3`, `music.mp3`, `clips/*.mp4` — медиа
- `QA-flags.md` — какие клипы заменить вручную
- `motion-notes.md` — чеклист motion-templates
- `metadata_de.json` — title/desc/tags
- `open-davinci.command` — двойной клик → DaVinci

## Стоимость production

| Компонент       | Цена/месяц    |
|-----------------|---------------|
| VPS DO Basic    | $12           |
| Hermes-4 LLM    | ~$5-15        |
| Deepgram        | ~$3-5         |
| FAL Flux        | ~$2-4         |
| ElevenLabs      | $50 (или Edge=$0) |
| GDrive          | $0 (free 15GB) |
| **Итого Edge**  | **~$22-36/мес** |
| **Итого 11Labs**| **~$72-86/мес** |

При 30 видео/мес → cost per video $0.7-2.9.
При 22-мин видео с CPM €15 на DE и 30k views = ~$10 → ROI многократный.

## Мониторинг

```bash
# Последний прогон
tail -50 ~/youtube-factory/logs/autorun.log

# Очередь
cat ~/youtube-factory/data/queue.json | python3 -m json.tool

# Сколько видео сделано
ls -1d ~/youtube-factory/data/*/ | wc -l

# Disk usage
du -sh ~/youtube-factory/data/
```

## Backup

Все daily выходы лежат в GDrive. Локально на VPS можно периодически чистить:
```bash
# Удалить папки старше 30 дней
find ~/youtube-factory/data -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
```
