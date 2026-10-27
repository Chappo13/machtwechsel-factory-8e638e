"""
Trending topic discovery with virality scoring and Russian translation.

Flow:
1. Load channel config (niche, search queries, history)
2. Search YouTube for competitors via yt-dlp
3. Filter: medium channels + recent long-form videos with good views
4. LLM analyzes patterns → generates ideas with virality %
5. Translate titles + hooks to Russian
6. Filter out topics from channel history (last N)
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta

import httpx


def _parse_json_array(text: str):
    """Достаёт JSON-массив идей из ответа LLM. Терпит ```json-обёртку, прозу вокруг
    и трейлинг-текст (хрупкий json.loads(response) падал → discover отдавал [])."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, list) else (v.get("ideas") if isinstance(v, dict) else None)
    except Exception:
        pass
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j > i:
        try:
            return json.loads(t[i:j + 1])
        except Exception:
            return None
    return None
from pathlib import Path
from typing import Optional

from backend.config import get_model_config, get_channel_config, get_channel_history, get_published_titles


# Общефинансовые/документальные слова — НЕ считаем их «сущностью» для дедупа
# (иначе любые две темы про «Milliarden/Betrug/Skandal» схлопнулись бы в дубль).
_DEDUP_STOPWORDS = {
    "milliarden", "millionen", "milliarde", "million", "dollar", "euro",
    "betrug", "skandal", "skandals", "geschichte", "unternehmen", "konzern",
    "konzerns", "finanzen", "finanz", "wirtschaft", "wirtschafts", "deutschland",
    "deutsche", "deutschen", "deutscher", "geheime", "geheimen", "korruption",
    "untergang", "aufstieg", "dunkle", "wahrheit", "warum", "zerstörte", "zerstört",
    "system", "systeme", "imperium", "pleite", "affäre", "affaere",
    "company", "companies", "financial", "finance", "documentary", "history",
    "scandal", "fraud", "biggest", "money", "billion", "collapse", "secret",
    "nearly", "destroyed", "greatest", "disaster", "rise", "fall", "story",
}


def _drop_published_ideas(ideas, published_titles):
    """Выкидывает идею-дубль уже опубликованного на канале видео. Два сигнала:
      1) token-Jaccard значимых слов ≥0.5 (близкие формулировки, напр. оба про Dieselskandal);
      2) общий ОТЛИЧИТЕЛЬНЫЙ токен (имя/сущность: длина ≥6, не общефинансовое слово) —
         ловит entity-совпадения вроде «Siemens», где Jaccard мал из-за разных формулировок.
    Это belt-and-suspenders к LLM-инъекции «не повторять эти темы»."""
    if not ideas or not published_titles:
        return ideas

    def toks(s):
        return set(w for w in re.sub(r"[^\w\s]", " ", (s or "").lower()).split() if len(w) > 3)

    pub = [t for t in (toks(p) for p in published_titles) if t]
    pub_entities = set()
    for pt in pub:
        pub_entities |= {w for w in pt if len(w) >= 6 and w not in _DEDUP_STOPWORDS}

    out = []
    for idea in ideas:
        title = idea.get("title_original", "") if isinstance(idea, dict) else ""
        it = toks(title)
        jaccard_dup = any(it and pt and len(it & pt) / min(len(it), len(pt)) >= 0.5 for pt in pub)
        entity_dup = bool(it & pub_entities and any(
            w in pub_entities for w in it if len(w) >= 6 and w not in _DEDUP_STOPWORDS))
        if jaccard_dup or entity_dup:
            logger.debug(f"dedup: выкинул идею (уже на канале): {title[:60]}")
        else:
            out.append(idea)
    return out
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)

# Filter defaults. max_subs смягчён: order=viewCount тянет крупные каналы, жёсткий
# 200k резал всё → viral_videos=0. 2M ловит реальные тренды ниши любого размера канала.
DEFAULT_MAX_SUBS = 2_000_000
DEFAULT_MIN_VIEWS = 15_000
DEFAULT_MAX_VIEWS = 50_000_000
DEFAULT_MIN_DURATION = 1200   # 20 minutes in seconds
DEFAULT_DAYS_BACK = 90        # last 3 months


async def find_viral_topics(
    lang: str,
    num_ideas: int = 10,
    max_subs: int = DEFAULT_MAX_SUBS,
    min_views: int = DEFAULT_MIN_VIEWS,
    max_views: int = DEFAULT_MAX_VIEWS,
    min_duration: int = DEFAULT_MIN_DURATION,
    days_back: int = DEFAULT_DAYS_BACK,
) -> dict:
    """
    Full pipeline: find viral videos → analyze → generate ideas with
    Russian translation and virality scores.

    Filters:
        max_subs: ignore channels with more subscribers (default 200k)
        min_views / max_views: view count range (default 50k–1M)
        min_duration: minimum video duration in seconds (default 1200 = 20 min)
        days_back: only videos published in the last N days (default 90 = 3 months)
    """
    channel = get_channel_config(lang)
    niche = channel["niche"]
    search_queries = channel.get("search_queries", [])
    # Дедуп: локальная история + РЕАЛЬНО опубликованные на YouTube-канале клиента
    # (главный источник «уже сделано» — чтобы не предлагать то, что уже на канале)
    published = get_published_titles(lang)
    seen, recent_topics = set(), []
    for t in list(get_channel_history(lang)) + published:
        key = (t or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            recent_topics.append(t)
    if published:
        logger.info(f"dedup: {len(published)} опубликованных видео канала учтено")

    cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")

    # Step 1: Find matching videos
    viral_videos = []
    # Параллельный поиск по всем запросам (раньше последовательно → ~16с, discover упирался
    # в gateway-timeout Railway). gather срезает до длительности самого долгого запроса.
    search_results = await asyncio.gather(
        *[_search_youtube(q, max_results=25, cutoff_date=cutoff_date, lang=lang) for q in search_queries],
        return_exceptions=True,
    )
    for results in search_results:
        if isinstance(results, Exception) or not results:
            continue
        for video in results:
            subs = video.get("subscriber_count", 0)
            views = video.get("view_count", 0)
            duration = video.get("duration", 0)
            upload_date = video.get("upload_date", "")  # YYYYMMDD or ""

            if subs > max_subs:
                continue
            if views < min_views or views > max_views:
                continue
            if duration < min_duration:
                continue
            # Date filter: skip if we know it's too old; include if date unknown
            if upload_date and upload_date < cutoff_date:
                continue

            viral_videos.append(video)

    # Deduplicate
    seen = set()
    unique = []
    for v in viral_videos:
        if v["title"] not in seen:
            seen.add(v["title"])
            unique.append(v)
    viral_videos = sorted(unique, key=lambda x: x.get("view_count", 0), reverse=True)[:40]

    logger.info(f"Found {len(viral_videos)} viral videos for {lang}/{niche}")

    if not viral_videos:
        ideas = await _generate_ideas_standalone(channel, lang, num_ideas, recent_topics)
        return {
            "viral_videos": [],
            "pattern_analysis": "Вирусные видео не найдены, идеи сгенерированы автономно",
            "ideas": _drop_published_ideas(ideas, published),
            "recent_topics": recent_topics,
        }

    # Step 2-3: Analyze patterns + generate ideas. Если LLM моргнул (non-JSON,
    # 429, таймаут) — НЕ отдаём пустой список: фолбэк на автономную генерацию,
    # чтобы точка входа сайта (выбор темы) всегда что-то возвращала.
    pattern_analysis = ""
    ideas = []
    try:
        pattern_analysis = await _analyze_patterns(viral_videos, niche, lang)
        ideas = await _generate_ideas_with_translation(
            viral_videos, pattern_analysis, channel, lang, num_ideas, recent_topics
        )
    except Exception as e:
        logger.warning(f"Анализ/генерация идей упали ({e}) → автономный фолбэк")

    if not ideas:
        logger.warning("Идей по конкурентам нет → автономная генерация")
        ideas = await _generate_ideas_standalone(channel, lang, num_ideas, recent_topics)
        if not pattern_analysis:
            pattern_analysis = "Идеи сгенерированы автономно (анализ конкурентов недоступен)"

    return {
        "viral_videos": viral_videos[:10],  # return top 10 for reference
        "pattern_analysis": pattern_analysis,
        "ideas": _drop_published_ideas(ideas, published),
        "recent_topics": recent_topics,
    }


YOUTUBE_API_KEY = os.getenv("YOUTUBE_DATA_API", "") or os.getenv("YOUTUBE_API_KEY", "")


def _iso8601_to_seconds(dur: str) -> int:
    """ISO 8601 длительность видео (PT#H#M#S) → секунды."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


async def _search_youtube_api(query: str, max_results: int, cutoff_date: str, lang: str) -> list[dict]:
    """Поиск через YouTube Data API v3 (надёжно с датацентр-IP, в отличие от yt-dlp).

    search.list → videos.list (views+длительность) → channels.list (подписчики).
    Это чинит и сломанные фильтры: yt-dlp --flat-playlist не отдаёт subs/duration.
    """
    base = "https://www.googleapis.com/youtube/v3"
    published_after = f"{cutoff_date[:4]}-{cutoff_date[4:6]}-{cutoff_date[6:8]}T00:00:00Z"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            rs = await client.get(f"{base}/search", params={
                "part": "snippet", "q": query, "type": "video", "order": "viewCount",
                "maxResults": min(max_results, 50), "publishedAfter": published_after,
                "relevanceLanguage": lang, "key": YOUTUBE_API_KEY,
            })
            if rs.status_code != 200:
                logger.warning(f"YT API search {rs.status_code}: {rs.text[:200]}")
                return []
            items = rs.json().get("items", [])
            snippets = {it["id"]["videoId"]: it["snippet"]
                        for it in items if it.get("id", {}).get("videoId")}
            vid_ids = list(snippets.keys())
            if not vid_ids:
                return []

            rv = await client.get(f"{base}/videos", params={
                "part": "statistics,contentDetails", "id": ",".join(vid_ids),
                "key": YOUTUBE_API_KEY,
            })
            vstats = {v["id"]: v for v in rv.json().get("items", [])} if rv.status_code == 200 else {}

            chan_ids = list({s.get("channelId") for s in snippets.values() if s.get("channelId")})
            subs = {}
            if chan_ids:
                rc = await client.get(f"{base}/channels", params={
                    "part": "statistics", "id": ",".join(chan_ids[:50]), "key": YOUTUBE_API_KEY,
                })
                if rc.status_code == 200:
                    for c in rc.json().get("items", []):
                        subs[c["id"]] = int(c.get("statistics", {}).get("subscriberCount", 0) or 0)
    except Exception as e:
        logger.warning(f"YT Data API search failed for '{query}': {e}")
        return []

    videos = []
    for vid in vid_ids:
        sn = snippets.get(vid, {})
        st = vstats.get(vid, {})
        videos.append({
            "title": sn.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "view_count": int(st.get("statistics", {}).get("viewCount", 0) or 0),
            "channel": sn.get("channelTitle", ""),
            "subscriber_count": subs.get(sn.get("channelId", ""), 0),
            "duration": _iso8601_to_seconds(st.get("contentDetails", {}).get("duration", "")),
            "upload_date": (sn.get("publishedAt", "") or "")[:10].replace("-", ""),
        })
    return videos


async def _search_youtube(query: str, max_results: int = 25,
                          cutoff_date: str = None, lang: str = "de") -> list[dict]:
    """Поиск вирусных видео. YouTube Data API (если есть ключ) иначе yt-dlp-фолбэк."""
    if YOUTUBE_API_KEY:
        cutoff = cutoff_date or (datetime.now() - timedelta(days=DEFAULT_DAYS_BACK)).strftime("%Y%m%d")
        vids = await _search_youtube_api(query, max_results, cutoff, lang)
        if vids:
            return vids
        logger.warning(f"YT Data API дал 0 по '{query}' → пробую yt-dlp")
    return await _search_youtube_ytdlp(query, max_results)


async def _search_youtube_ytdlp(query: str, max_results: int = 25) -> list[dict]:
    """Search YouTube via yt-dlp. Returns videos with duration and upload_date."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--no-download",
        # Pre-filter by duration on yt-dlp side (faster than Python-side only)
        "--match-filter", f"duration>={DEFAULT_MIN_DURATION}",
        "--print", (
            '{"title":"%(title)s","url":"%(url)s",'
            '"view_count":%(view_count)s,"channel":"%(channel)s",'
            '"subscriber_count":%(channel_follower_count)s,'
            '"duration":%(duration)s,"upload_date":"%(upload_date)s"}'
        ),
        f"ytsearch{max_results}:{query}",
    ]
    try:
        # to_thread: не блокировать event loop (запросы идут в параллельном gather)
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=90)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                video = json.loads(line)
                video["view_count"] = video.get("view_count") or 0
                video["subscriber_count"] = video.get("subscriber_count") or 0
                video["duration"] = video.get("duration") or 0
                video["upload_date"] = str(video.get("upload_date") or "")
                videos.append(video)
            except json.JSONDecodeError:
                continue
        return videos
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"yt-dlp search failed for '{query}': {e}")
        return []


async def _analyze_patterns(videos: list[dict], niche: str, lang: str) -> str:
    """Analyze title patterns from viral videos."""
    model_config = get_model_config("script_generation")

    video_list = "\n".join([
        f"- \"{v['title']}\" — {v['view_count']:,} views, "
        f"{v.get('subscriber_count', 0):,} subs, "
        f"{int(v.get('duration', 0)) // 60}min, "
        f"uploaded: {v.get('upload_date', '?')}"
        for v in videos[:30]
    ])

    lang_name = {"de": "German", "es": "Spanish", "vi": "Vietnamese"}.get(lang, lang)

    prompt = f"""Analyze these YouTube videos from SMALL/MEDIUM channels (≤200K subs) in {niche} niche ({lang_name}).
All videos are 20+ minutes long, published in the last 3 months, with 50K–1M views.

{video_list}

Identify:
1. TITLE PATTERNS: What structures got most views? (numbers, "Warum", "Wie", scandal words etc.)
2. EMOTIONAL TRIGGERS: Which emotions drive clicks in long-form documentary format?
3. TOPIC SWEET SPOTS: What sub-topics performed best? (rise&fall, scandal, hidden systems, etc.)
4. FORMAT INSIGHTS: What makes these 20+ min videos retain viewers?
5. TOP 3 TITLE FORMULAS that work best for long-form documentary

Be specific with numbers and examples."""

    return await call_llm(
        prompt=prompt,
        model=model_config["primary"],
        temperature=0.5,
        max_tokens=3000,
    )


async def _generate_ideas_with_translation(
    videos: list[dict],
    analysis: str,
    channel: dict,
    lang: str,
    num_ideas: int,
    recent_topics: list[str],
) -> list[dict]:
    """Generate ideas with virality score and Russian translation."""
    model_config = get_model_config("script_generation")

    lang_name = {"de": "Deutsch", "es": "Español", "vi": "Tiếng Việt"}.get(lang, lang)
    niche = channel["niche"]

    # Build recent topics block
    recent_block = ""
    if recent_topics:
        recent_block = f"""
ВАЖНО: Эти темы уже были на канале (НЕ повторять):
{chr(10).join(f'- {t}' for t in recent_topics)}
"""

    # Build source videos block
    source_block = "\n".join([
        f"- \"{v['title']}\" — {v['view_count']:,} views (url: {v.get('url', 'N/A')})"
        for v in videos[:20]
    ])

    guide, cats = _channel_format_block(channel, lang)
    prompt = f"""Based on competitor analysis in {niche} niche:

{guide}

Pattern analysis:
{analysis}

Top competitor videos:
{source_block}
{recent_block}

Generate EXACTLY {num_ideas} unique video ideas — ALL in THIS channel's format (same angle/style as the example titles above). For EACH idea provide ALL fields:

- "title_original": Title in {lang_name} (max 70 chars, same style as the channel examples)
- "title_ru": Перевод названия на русский язык
- "category": One of: {cats}
- "hook": One-sentence hook in {lang_name}
- "hook_ru": Перевод хука на русский
- "virality_score": 0-100 (how likely to go viral, based on patterns)
- "why_viral": Why this topic would perform (1 sentence, на русском)
- "source_url": URL of the competitor video that inspired this idea (or null)
- "source_views": View count of that video (or null)

Virality scoring guide:
- 90-100: Proven pattern + trending topic + strong emotion
- 70-89: Good pattern + interesting topic
- 50-69: Decent topic but weaker hook
- <50: Generic topic

Return ONLY valid JSON array. No markdown."""

    response = await call_llm(
        prompt=prompt,
        model=model_config["primary"],
        temperature=0.8,
        max_tokens=12000,
    )

    raw_ideas = _parse_json_array(response)
    if not raw_ideas:
        logger.error("Failed to parse ideas JSON (with-translation)")
        return []

    # Normalize and sort by virality
    ideas = []
    for idea in raw_ideas:
        ideas.append({
            "title_original": idea.get("title_original", ""),
            "title_ru": idea.get("title_ru", ""),
            "category": idea.get("category", ""),
            "hook": idea.get("hook", ""),
            "hook_ru": idea.get("hook_ru", ""),
            "virality_score": min(100, max(0, int(idea.get("virality_score", 50)))),
            "why_viral": idea.get("why_viral", ""),
            "source_video": idea.get("source_url"),
            "source_views": idea.get("source_views"),
        })

    ideas.sort(key=lambda x: x["virality_score"], reverse=True)
    logger.info(f"Generated {len(ideas)} ideas, top virality: {ideas[0]['virality_score'] if ideas else 0}%")
    return ideas


def _channel_format_block(channel: dict, lang: str) -> tuple[str, str]:
    """Format-гайд для генератора идей из themes.yaml канала: описание + реальные
    example_topics (образец формата) + допустимые категории (ключи тем). Чтобы идеи
    шли в ФОРМАТЕ канала, а не «что вообще вирусит на языке». Возвращает (guide, cats)."""
    from backend.config import get_theme_config
    try:
        themes = get_theme_config(lang) or {}
    except Exception:
        themes = {}
    theme_lines, example_lines = [], []
    for key, t in themes.items():
        if not isinstance(t, dict):
            continue
        theme_lines.append(f"- {key}: {t.get('description', '')}")
        for ex in (t.get("example_topics") or [])[:4]:
            example_lines.append(f"- {ex}")
    cats = ", ".join(themes.keys()) or channel.get("niche", "general")
    guide = (
        f"CHANNEL: {channel.get('name', channel.get('niche', ''))}\n"
        f"WHAT THIS CHANNEL IS: {channel.get('description', '')}\n\n"
        f"CONTENT THEMES (pick \"category\" from these keys ONLY: {cats}):\n"
        + "\n".join(theme_lines)
        + "\n\nFORMAT RULE — every idea MUST match THIS channel's format. Study these REAL "
        "example titles and write NEW ones in the SAME angle and style. Do NOT drift into "
        "other genres (no drama, no story-recaps, no fiction) unless the examples themselves are:\n"
        + "\n".join(example_lines[:12])
    )
    return guide, cats


async def _generate_ideas_standalone(
    channel: dict, lang: str, num_ideas: int, recent_topics: list[str]
) -> list[dict]:
    """Fallback: generate ideas without competitor data."""
    model_config = get_model_config("script_generation")
    lang_name = {"de": "Deutsch", "es": "Español", "vi": "Tiếng Việt"}.get(lang, lang)
    niche = channel["niche"]

    recent_block = ""
    if recent_topics:
        recent_block = f"\nНЕ повторять эти темы:\n" + "\n".join(f"- {t}" for t in recent_topics)

    guide, cats = _channel_format_block(channel, lang)
    prompt = f"""Generate {num_ideas} unique, viral video ideas for this YouTube channel — ALL matching its format.

{guide}
{recent_block}

For each idea: title_original (in {lang_name}, same style as the examples), title_ru (русский), category (one of: {cats}), hook, hook_ru, virality_score (0-100), why_viral (русский).
Return JSON array only."""

    response = await call_llm(
        prompt=prompt, model=model_config["primary"],
        temperature=0.9, max_tokens=8000,
    )
    return _parse_json_array(response) or []


async def fetch_transcripts(
    video_urls: list[str],
    lang: str = "de",
    max_chars_per_video: int = 5000,
) -> list[dict]:
    """
    Download auto-generated transcripts for up to 3 YouTube videos.

    Uses yt-dlp to grab auto-captions (prefers target lang, falls back to English).
    Returns list of {url, title, transcript} dicts — empty list if nothing found.
    """
    results = []
    sub_lang = f"{lang},en"

    with tempfile.TemporaryDirectory() as tmp_dir:
        for url in video_urls[:3]:
            try:
                out_tpl = str(Path(tmp_dir) / "%(id)s")
                cmd = [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--sub-lang", sub_lang,
                    "--sub-format", "vtt",
                    "--skip-download",
                    "--no-playlist",
                    "--print", "%(title)s",
                    "-o", out_tpl,
                    url,
                ]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                title = r.stdout.strip().split("\n")[0] if r.stdout.strip() else url

                vtt_files = sorted(Path(tmp_dir).glob("*.vtt"))
                if not vtt_files:
                    logger.warning(f"No transcript found: {url}")
                    continue

                raw = vtt_files[0].read_text(encoding="utf-8", errors="ignore")
                transcript = _clean_vtt(raw)[:max_chars_per_video]
                vtt_files[0].unlink()

                if len(transcript) < 200:
                    logger.warning(f"Transcript too short ({len(transcript)} chars): {url}")
                    continue

                results.append({"url": url, "title": title, "transcript": transcript})
                logger.info(f"Transcript OK: '{title[:60]}' — {len(transcript)} chars")

            except Exception as e:
                logger.warning(f"fetch_transcripts failed for {url}: {e}")

    return results


def _clean_vtt(vtt_text: str) -> str:
    """Parse VTT subtitle file → clean plain text, no timestamps, no duplicates."""
    seen: set[str] = set()
    lines: list[str] = []

    for line in vtt_text.splitlines():
        line = line.strip()
        # Skip VTT header, timestamps, cue identifiers, empty lines
        if (not line
                or line.startswith("WEBVTT")
                or line.startswith("NOTE")
                or re.match(r"^\d{2}:\d{2}:\d{2}", line)
                or re.match(r"^\d+$", line)):
            continue
        # Remove inline HTML tags (<c>, <00:00:00.000>)
        line = re.sub(r"<[^>]+>", "", line).strip()
        if len(line) < 4:
            continue
        # Auto-captions duplicate a lot of lines — deduplicate
        if line not in seen:
            seen.add(line)
            lines.append(line)

    return " ".join(lines)
