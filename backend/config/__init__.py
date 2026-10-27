"""YouTube Factory configuration loader."""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
CLIP_CACHE_DIR = DATA_DIR / "clip_cache"
MUSIC_DIR = DATA_DIR / "music"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure dirs exist
for d in [OUTPUT_DIR, CLIP_CACHE_DIR, MUSIC_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    """Текущее время UTC в ISO с суффиксом 'Z'. Фронт через toLocaleString сам
    покажет его в таймзоне браузера пользователя (у клиента — Вьетнам, UTC+7),
    без хардкода зоны на бэке. Раньше писали наивное серверное (UTC) без 'Z' —
    фронт трактовал как локальное → время было сдвинуто."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_yaml(name: str) -> dict:
    """Load a YAML config file by name."""
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_voice_config(lang: str) -> dict:
    """Get voice configuration for a language."""
    config = load_yaml("voices")
    voices = config.get("voices", {})
    if lang not in voices:
        raise ValueError(f"No voice config for language: {lang}")
    return {**voices[lang], "api": config.get("api", {})}


def get_model_config(task: str) -> dict:
    """Get LLM model config for a specific task."""
    config = load_yaml("models")
    models = config.get("models", {})
    if task not in models:
        raise ValueError(f"No model config for task: {task}")
    return models[task]


def get_image_config() -> dict:
    """Конфиг генератора картинок (doodle-сцены): endpoint + params. Swappable
    через models.yaml → image_generation без правки кода. Пусто → stick_figure.py
    берёт встроенные дефолты."""
    config = load_yaml("models")
    return config.get("image_generation", {})


def get_theme_config(lang: str) -> dict:
    """Get content themes for a language."""
    config = load_yaml("themes")
    themes = config.get("themes", {})
    if lang not in themes:
        raise ValueError(f"No theme config for language: {lang}")
    return themes[lang]


def get_patterns(lang: str) -> dict:
    """Get retention hooks and forbidden patterns for a language."""
    config = load_yaml("patterns")
    hooks = config.get("retention_hooks", {})
    quality = config.get("quality", {})
    if lang not in hooks:
        raise ValueError(f"No patterns for language: {lang}")
    return {"hooks": hooks[lang], "quality": quality}


# Environment shortcuts
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GONKA_API_KEY = os.getenv("GONKA_API_KEY", "")
VOICER_API_KEY = os.getenv("VOICER_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")


def get_channel_config(lang: str) -> dict:
    """Get channel profile for a language."""
    config = load_yaml("channels")
    channels = config.get("channels", {})
    if lang not in channels:
        raise ValueError(f"No channel config for: {lang}")
    return channels[lang]


def get_music_library() -> list:
    """Get manually curated music tracks."""
    config = load_yaml("channels")
    return config.get("music_library", {}).get("tracks", [])


def get_published_titles(lang: str, refresh_hours: int = 12) -> list[str]:
    """Названия видео, УЖЕ опубликованных на YouTube-канале клиента — источник
    «уже сделано» для дедупа тем. Тянет через YouTube Data API (работает с Railway,
    в отличие от yt-dlp-скрейпинга), кэширует в data/channel_videos_{lang}.json.
    Фолбэк: при сбое API — отдаём кэш (даже устаревший). Нет канала/ключа → []."""
    import json, time, urllib.request, urllib.parse

    try:
        channel = get_channel_config(lang)
    except Exception:
        return []
    channel_id = (channel or {}).get("youtube_channel_id", "")
    if not channel_id:
        return []

    cache_file = DATA_DIR / f"channel_videos_{lang}.json"
    cached = None
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            age_h = (time.time() - cached.get("fetched_at", 0)) / 3600
            if age_h < refresh_hours and cached.get("titles"):
                return cached["titles"]
        except Exception:
            cached = None

    api_key = os.getenv("YOUTUBE_DATA_API", "")
    if not api_key:
        return (cached or {}).get("titles", []) if cached else []

    def _get(url: str) -> dict:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)

    try:
        uploads = "UU" + channel_id[2:]  # channel UCxxx → uploads playlist UUxxx
        titles, page = [], ""
        for _ in range(5):  # до 250 видео
            q = urllib.parse.urlencode({
                "part": "snippet", "playlistId": uploads, "maxResults": 50,
                "key": api_key, **({"pageToken": page} if page else {}),
            })
            data = _get(f"https://www.googleapis.com/youtube/v3/playlistItems?{q}")
            for it in data.get("items", []):
                t = (it.get("snippet", {}) or {}).get("title", "").strip()
                if t and t.lower() != "private video" and t.lower() != "deleted video":
                    titles.append(t)
            page = data.get("nextPageToken", "")
            if not page:
                break
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(
            {"fetched_at": time.time(), "titles": titles}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return titles
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"get_published_titles({lang}) failed: {e}")
        return (cached or {}).get("titles", []) if cached else []


def get_channel_history(lang: str) -> list[str]:
    """Get list of recent video topics for the channel to avoid repeats."""
    channel = get_channel_config(lang)
    window = channel.get("history_window", 10)
    history_file = DATA_DIR / f"history_{lang}.json"
    if not history_file.exists():
        return []
    import json
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    return history[-window:]


def add_to_channel_history(lang: str, topic: str):
    """Add a completed video topic to channel history."""
    import json
    history_file = DATA_DIR / f"history_{lang}.json"
    history = []
    if history_file.exists():
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    history.append(topic)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── Архив найденных тем (персистентный, переживает рестарты; DATA_DIR — том) ──

def _topic_id(lang: str, title: str) -> str:
    import hashlib, re
    norm = re.sub(r"\s+", " ", (title or "").strip().lower())
    return hashlib.sha1(f"{lang}:{norm}".encode("utf-8")).hexdigest()[:12]


def get_topic_archive(lang: str) -> list[dict]:
    """Все ранее отобранные темы канала — чтобы не искать заново. Отсортированы по virality_score."""
    import json
    f = DATA_DIR / f"topics_{lang}.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        topics = data.get("topics", []) if isinstance(data, dict) else []
        return sorted(topics, key=lambda t: t.get("virality_score", 0), reverse=True)
    except Exception:
        return []


def save_topics_to_archive(lang: str, ideas: list[dict]) -> list[dict]:
    """Мержит найденные идеи в архив с дедупом по id (lang+normalize(title)).
    Темы НЕ теряются между запусками discover. Возвращает полный архив по убыванию скоринга."""
    import json, time
    f = DATA_DIR / f"topics_{lang}.json"
    existing = {t["id"]: t for t in get_topic_archive(lang) if t.get("id")}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for idea in ideas or []:
        title = (idea.get("title_original") or "").strip()
        if not title:
            continue
        tid = _topic_id(lang, title)
        if tid in existing:
            existing[tid]["virality_score"] = max(
                existing[tid].get("virality_score", 0), idea.get("virality_score", 0))
            continue
        existing[tid] = {
            "id": tid,
            "title_original": title,
            "title_ru": idea.get("title_ru", ""),
            "category": idea.get("category", ""),
            "hook": idea.get("hook", ""),
            "hook_ru": idea.get("hook_ru", ""),
            "virality_score": idea.get("virality_score", 50),
            "why_viral": idea.get("why_viral", ""),
            "source_video": idea.get("source_video"),
            "source_views": idea.get("source_views"),
            "status": "new",
            "discovered_at": now,
            "used_at": None,
        }
    topics = sorted(existing.values(), key=lambda t: t.get("virality_score", 0), reverse=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"topics": topics}, ensure_ascii=False, indent=2), encoding="utf-8")
    return topics


def mark_topic_used(lang: str, title: str):
    """Помечает тему использованной (из неё сделали сценарий/видео) — для UI-фильтра."""
    import json, time
    f = DATA_DIR / f"topics_{lang}.json"
    topics = get_topic_archive(lang)
    if not topics:
        return
    tid = _topic_id(lang, title)
    changed = False
    for t in topics:
        if t.get("id") == tid and t.get("status") != "used":
            t["status"] = "used"
            t["used_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            changed = True
    if changed:
        f.write_text(json.dumps({"topics": topics}, ensure_ascii=False, indent=2), encoding="utf-8")
