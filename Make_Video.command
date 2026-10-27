#!/bin/bash
# Двойной клик → генерация видео по теме.
# Меняй переменные TOPIC / LANG / DURATION прямо в этом файле.
cd "$(dirname "$0")"

# ─── НАСТРОЙ ЗДЕСЬ ──────────────────────────────────────────────
TOPIC="Wie Wirecard Deutschland täuschte"
LANG="de"
DURATION=3   # минут (3 для теста, 22 для full)
# ───────────────────────────────────────────────────────────────

if [ ! -d .venv ]; then
  echo "✗ Сначала запусти Setup_Mac.command"
  read -n1; exit 1
fi

source .venv/bin/activate
echo "== YouTube Factory =="
echo "  Topic:    $TOPIC"
echo "  Lang:     $LANG"
echo "  Duration: $DURATION min"
echo "  Mode:     fcpxml (для DaVinci)"
echo ""

python3 -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()
from backend.pipeline.orchestrator import VideoTask, Pipeline
task = VideoTask(topic='$TOPIC', lang='$LANG', duration_minutes=$DURATION, output_mode='fcpxml')
asyncio.run(Pipeline().run(task))
print()
print('=' * 60)
print(f'✓ Готово. Папка:')
print(f'  {task.workspace}')
print('=' * 60)
print(f'Открой в DaVinci: cd \"{task.workspace}\" && open open-davinci.command')
"

echo ""
read -n1 -r -p "Enter чтобы закрыть..."
