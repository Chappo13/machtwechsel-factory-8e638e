#!/bin/bash
# Двойной клик → перевыровнять scene_plan по обновлённому voice.mp3.
# Используй ПОСЛЕ того как заменил голос (например через ElevenLabs UI).
cd "$(dirname "$0")"
source .venv/bin/activate

# Найди самую свежую папку с видео
LATEST=$(ls -1dt data/*/ 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
  echo "✗ Нет папок в data/. Сначала запусти Make_Video.command"
  read -n1; exit 1
fi

echo "== Realign =="
echo "  Folder: $LATEST"
echo ""

python3 -c "
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from backend.pipeline.align_scenes import realign_scene_plan

ws = Path('$LATEST')
print(f'Folder: {ws}')
asyncio.run(realign_scene_plan(
    voice_path=ws/'voice.mp3',
    scene_plan_path=ws/'scene_plan.json',
    lang='de',
))
print('✓ scene_plan_aligned.json обновлён.')
print('  Для перегенерации FCPXML — нужен второй прогон, скажу позже.')
"

read -n1 -r -p "Enter чтобы закрыть..."
