#!/bin/bash
# One-shot install для Ubuntu VPS (testing on 24.04).
# Использование: bash install-on-vps.sh
set -euo pipefail

REPO_DIR="${HOME}/youtube-factory"

echo "== YT Factory · VPS install =="

# 1. System deps
if ! command -v ffmpeg &>/dev/null; then
  echo "▸ ffmpeg..."
  sudo apt-get update -y
  sudo apt-get install -y ffmpeg python3.11 python3.11-venv git
fi

# 2. Clone if needed
if [ ! -d "$REPO_DIR" ]; then
  echo "▸ cloning repo..."
  git clone https://github.com/Chappo13/youtube-factory.git "$REPO_DIR"
fi

cd "$REPO_DIR"
git checkout feat/fcpxml-davinci-export
git pull

# 3. venv + deps
if [ ! -d ".venv" ]; then
  python3.11 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt
pip install edge-tts python-dotenv

# 4. .env template
if [ ! -f .env ]; then
  cat > .env <<'ENVEOF'
# Заполни значениями из AIzdec /settings → 🔑
OPENROUTER_API_KEY=
DEEPGRAM_API_KEY=
FALAPI=
PEXELS_API_KEY=
PIXABAY_API_KEY=
# Для уведомлений в Telegram (опционально):
TELEGRAM_BOT_TOKEN=
OWNER_CHAT_ID=
# Для авто-выгрузки на GDrive (опционально):
GDRIVE_FOLDER_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ENVEOF
  echo "▸ .env шаблон создан — заполни значения"
fi

mkdir -p logs data

# 5. systemd setup (опционально)
echo ""
echo "Готово."
echo ""
echo "Дальше:"
echo "  1. Заполни .env"
echo "  2. Тест: .venv/bin/python3 autorun.py --topic 'Test' --lang de --duration 3"
echo "  3. Cron: добавь строку из deploy/crontab.example в crontab -e"
echo "  4. Или systemd: sudo cp deploy/youtube-factory.{service,timer} /etc/systemd/system/"
echo "                  sudo systemctl daemon-reload"
echo "                  sudo systemctl enable --now youtube-factory.timer"
