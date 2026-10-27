#!/bin/bash
# Двойной клик → первичная установка зависимостей.
# Запускать ОДИН РАЗ при первом клонировании.
cd "$(dirname "$0")"
set -e

echo "== YouTube Factory · Setup =="
echo ""

if ! command -v brew &>/dev/null; then
  echo "▸ Устанавливаю Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

echo "▸ Устанавливаю ffmpeg + python@3.11 (если ещё нет)..."
brew install ffmpeg python@3.11 || true

echo "▸ Создаю venv..."
python3.11 -m venv .venv 2>/dev/null || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip --quiet

echo "▸ Устанавливаю Python-зависимости..."
pip install -r requirements.txt
pip install edge-tts python-dotenv

if [ ! -f .env ]; then
  echo "▸ Создаю .env шаблон..."
  cat > .env <<'ENVEOF'
# Скопируй значения из AIzdec /settings → 🔑
OPENROUTER_API_KEY=
DEEPGRAM_API_KEY=
FALAPI=
PEXELS_API_KEY=
PIXABAY_API_KEY=
# VOICER_API_KEY=  опционально, для ElevenLabs (если нет — используется Edge TTS)
# GDRIVE_FOLDER_ID=  опционально для авто-выгрузки на Google Drive
ENVEOF
  echo "  → создан .env, открой и заполни значения"
fi

# Помечаем .venv как не-синхронизируемая iCloud
if [ ! -e .venv.nosync ]; then
  mv .venv .venv.nosync && ln -s .venv.nosync .venv
fi

echo ""
echo "✓ Setup готов."
echo "  1. Открой .env и впиши ключи (значения из AIzdec /settings)"
echo "  2. Двойной клик на Make_Video.command чтобы сгенерировать первое видео"
echo ""
read -n1 -r -p "Enter чтобы закрыть..."
