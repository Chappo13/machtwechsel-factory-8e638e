#!/usr/bin/env python3
"""
autorun.py — production runner для cron / systemd.

Workflow:
  1. Прочитать data/queue.json (список тем по приоритету)
  2. Взять первую неначатую тему
  3. Прогнать Pipeline
  4. Пометить тему как done
  5. Если queue пустая — discover trending (топ-3 идеи), добавить в queue,
     уведомить владельца чтобы одобрил перед следующим прогоном

CLI:
  python3 autorun.py                  # один прогон (берёт первую тему)
  python3 autorun.py --discover       # только discover trending (без прогона)
  python3 autorun.py --topic "..." --lang de --duration 22   # явная тема

Crontab пример (запуск раз в день в 4 утра):
  0 4 * * * cd ~/youtube-factory && /usr/bin/python3 autorun.py >> logs/autorun.log 2>&1
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Repo root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("autorun")

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
QUEUE = DATA / "queue.json"
LOGS = REPO / "logs"
LOGS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)


def load_queue() -> list:
    if not QUEUE.exists():
        return []
    try:
        return json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"queue.json parse error: {e}")
        return []


def save_queue(items: list):
    QUEUE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def pick_next(queue: list) -> Optional[dict]:
    for item in queue:
        if item.get("status") != "done":
            return item
    return None


async def run_one(topic: str, lang: str, duration: int) -> dict:
    from backend.pipeline.orchestrator import VideoTask, Pipeline

    task = VideoTask(
        topic=topic,
        lang=lang,
        duration_minutes=duration,
        output_mode="fcpxml",
    )
    pipeline = Pipeline()
    logger.info(f"START topic='{topic}' lang={lang} duration={duration}min")
    await pipeline.run(task)
    logger.info(f"DONE  workspace={task.workspace}")
    return {
        "task_id": task.task_id,
        "workspace": str(task.workspace),
        "gdrive_url": task.gdrive_url,
    }


async def discover_topics(lang: str = "de", count: int = 3) -> list:
    """Discover viral topics, add to queue with status=pending."""
    from backend.scrapers.trending import find_viral_topics

    logger.info(f"Discovering {count} viral topics for {lang}...")
    result = await find_viral_topics(lang=lang, num_ideas=count)
    ideas = result.get("ideas", [])[:count]

    queue = load_queue()
    new_items = []
    for idea in ideas:
        item = {
            "topic": idea.get("title_original") or idea.get("title_ru") or idea.get("title") or idea.get("topic"),
            "lang": lang,
            "duration_minutes": 22,
            "virality_score": idea.get("virality_score"),
            "added_at": datetime.utcnow().isoformat() + "Z",
            "status": "pending_approval",   # требует одобрения владельца
        }
        if item["topic"]:
            queue.append(item)
            new_items.append(item)

    save_queue(queue)
    logger.info(f"Added {len(new_items)} topics to queue (pending_approval)")
    return new_items


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true",
                        help="Discover trending topics, add to queue (без прогона)")
    parser.add_argument("--topic", help="Явная тема (skip queue)")
    parser.add_argument("--lang", default="de", help="Язык (de/es/en)")
    parser.add_argument("--duration", type=int, default=22, help="Длительность в минутах")
    args = parser.parse_args()

    # Mode 1: explicit topic
    if args.topic:
        try:
            result = await run_one(args.topic, args.lang, args.duration)
            print(json.dumps(result, indent=2))
            return 0
        except Exception:
            logger.error(f"FAILED: {traceback.format_exc()}")
            return 1

    # Mode 2: discover only
    if args.discover:
        await discover_topics(lang=args.lang)
        return 0

    # Mode 3: pick from queue
    queue = load_queue()
    item = pick_next(queue)
    if not item:
        logger.info("Queue empty — discovering new topics...")
        await discover_topics(lang=args.lang)
        logger.info("Discovery done. Approve topics in queue.json then rerun.")
        return 0

    if item.get("status") == "pending_approval":
        logger.warning(f"Top topic '{item['topic']}' is pending_approval. Skip.")
        # Try to find first approved
        approved = next((i for i in queue if i.get("status") == "approved"), None)
        if not approved:
            logger.info("No approved topics. Exit.")
            return 0
        item = approved

    item["status"] = "running"
    item["started_at"] = datetime.utcnow().isoformat() + "Z"
    save_queue(queue)

    try:
        result = await run_one(item["topic"], item["lang"], item.get("duration_minutes", 22))
        item["status"] = "done"
        item["done_at"] = datetime.utcnow().isoformat() + "Z"
        item["result"] = result
    except Exception:
        item["status"] = "failed"
        item["error"] = traceback.format_exc()[:2000]
        logger.error(f"FAILED: {traceback.format_exc()}")
    finally:
        save_queue(queue)

    return 0 if item["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
