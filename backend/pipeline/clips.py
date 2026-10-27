"""
Stock clip sourcing and scene planning.

Features:
- Scene plan generation from script + voiceover duration
- Multi-source clip search (Pexels, Pixabay, Wikimedia, Coverr)
- Vision scoring — verify clip relevance to narration
- SQLite cache (7-day TTL)
- Fallback: Ken Burns effect on photos when video not found
"""

import asyncio
import json
import logging
import re
from collections import deque
from pathlib import Path
from typing import Optional

from backend.config import get_model_config
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)


def _extract_scenes_json(response: str):
    """Толерантный разбор JSON-массива сцен от LLM: снимает ```-обёртку, вырезает
    от первого '[' до последнего ']', чинит трейлинг-запятые. Строгий json.loads
    падал на мелком синтаксис-слипе большого scene plan и валил весь прогон."""
    t = (response or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("["), t.rfind("]")
    if i != -1 and j > i:
        t = t[i:j + 1]
    t = re.sub(r",(\s*[}\]])", r"\1", t)  # трейлинг-запятые перед } или ]
    return json.loads(t)


async def plan_scenes(
    script: str,
    topic: str,
    lang: str,
    total_duration: float,
) -> list[dict]:
    """
    Generate scene plan from script.
    
    Splits script into scenes, each with:
    - start/end timestamps
    - narration text
    - search queries for stock footage
    
    Args:
        script: Full script text
        topic: Video topic
        lang: Language code
        total_duration: Voiceover duration in seconds
    
    Returns:
        List of scene dicts with timestamps and queries
    """
    model_config = get_model_config("scene_tagging")
    
    prompt = f"""You are a documentary video editor. Split this script into scenes. For EACH
scene, FIRST describe what the viewer literally SEES, THEN choose how to realize it.

Topic: {topic}
Total video duration: {total_duration:.0f} seconds ({total_duration/60:.1f} minutes)

For each scene provide, IN THIS ORDER:
1. "start", "end" — timestamps in seconds
2. "text" — the narration for this scene (verbatim; needed for voice alignment)
3. "mood" — dramatic | calm | tense | uplifting | dark | neutral
4. "on_screen" — ONE concrete English sentence: what the viewer literally sees this moment.
   e.g. "A well-dressed doctor leaving a clinic with a suitcase",
        "The figure 295,000 emphasized as a bold headline number",
        "An archival 1989 photo of crowds at the fallen Berlin Wall".
5. "medium" — how to realize on_screen. Pick the BEST fit for THIS scene (mix freely for
   variety — a rich video alternates types, never 4+ of the same in a row):
   - "stock_video"         → filmable real-life b-roll (people, places, action)
   - "image"               → a real STILL photo fits better: archival/historical, a portrait,
                             a document/headline (gets Ken Burns motion)
   - "concept"             → a CODE-DRAWN icon + short caption for a CONCEPT / METAPHOR /
                             EMOTION / abstract idea stock can't film and no real photo exists
                             (corruption, a lie, pressure, "a cycle of money"). Put the icon id
                             in remotion_data.icon from THIS set only: [money, growth, crash,
                             person, company, document, warning, justice, time, lock, network,
                             globe, mask, search, question, chain]. If NONE fits the idea,
                             use stock_video instead — do NOT force a concept card.
   - "infographic_counter" → the POINT is ONE big number stated in this scene's text
   - "infographic_chart"   → a trend over time (>=2 {{year,value}} points named in the text)
   - "infographic_split"   → a direct A-vs-B comparison (numbers OR short text, from the text)
   - "infographic_stat"    → 2-4 KPI figures stated together in the text
   - "infographic_ranked"  → a ranking / top-N list with values, all from the text
   - "infographic_timeline"→ a chronology of dated events (>=2 years named in the text)
   - "infographic_table"   → a multi-row A-vs-B table (vorher/nachher, two versions)
   - "infographic_title"   → intro/outro/chapter card, or a short statement on a clean card
   - "infographic_quote"   → a verbatim quote / court ruling / definition (the exact words)
   - "infographic_flow"    → money/transfer/relationship A→B ("von X nach Y"): place NAMES only
6. "queries" — for stock_video/image: 3 English search queries derived from on_screen.
   Provide these for infographic scenes too (used as a fallback).
   STOCK QUERIES NEVER contain person names, company names, brands or logos
   ("Markus Braun portrait", "Wirecard headquarters" — stock sites have NO such
   footage, the search degrades to random clips). Describe the GENERIC visual
   instead: "business executive dark suit boardroom", "modern corporate office
   tower Germany". Scenes that NEED a specific person/brand → medium "image"
   (real photo) or an infographic.
7. "remotion_data" — REQUIRED for infographic_*/concept. EVERY number, year, place, name or
   quote here MUST appear, in words, in THIS scene's narration text. If you cannot point to it
   in the text, do NOT use an infographic — use stock_video with text_overlay. NEVER provide
   pixel coordinates — the renderer positions everything.
   - counter:  {{"from":0,"to":<int>,"suffix":"","label":"<caption>"}}
   - chart:    {{"data":[{{"year":<int>,"value":<int>}}],"title":"<t>","yLabel":"<y>"}}
   - split (numeric): {{"leftValue":<int>,"leftLabel":"<A>","rightValue":<int>,"rightLabel":"<B>","title":"<t>"}}
   - split (textual): {{"leftCountry":"<A>","leftValue":"<str>","rightCountry":"<B>","rightValue":"<str>"}}
   - stat:     {{"title":"<t>","items":[{{"value":<int>,"label":"<l>","suffix":""}}]}}  (2-4 items)
   - ranked:   {{"title":"<t>","items":[{{"label":"<l>","value":<int>}}],"suffix":""}}
   - timeline: {{"title":"<t>","events":[{{"year":<int>,"label":"<l>"}}]}}
   - table:    {{"title":"<t>","columns":["<A>","<B>"],"rows":[{{"label":"<l>","a":"<..>","b":"<..>"}}]}}
   - title:    {{"title":"<text>","subtitle":"<optional>"}}
   - quote:    {{"quote":"<verbatim words from the text>","source":"<who/when, optional>"}}
   - flow:     {{"fromLabel":"<place A>","toLabel":"<place B>","amount":"<opt>","direction":"oneway"}}
   - concept:  {{"icon":"<id from the allowed set>","caption":"<short caption>"}}
8. "text_overlay" — for stock_video/image scenes that state a KEY statistic, a SHORT
   caption to burn on screen (e.g. "295.000 Fortzüge", "+9% vs 2024"). Keeps the number
   visible over b-roll = trust + retention. Use the script's language. "" if no key stat.

RULES — medium FOLLOWS from on_screen, do not default to counters:
- Most scenes are "stock_video". Use infographic only when the data/statement IS the scene.
- Prefer "image" for anything historical/archival/portrait/document/headline/map —
  stock video won't have it (this is what avoided hallucinated AI footage before).
- A number mentioned in passing inside a filmable moment → stock_video/image, NOT a counter.
- Money/transfer between two places ("von X nach Y") → ONE "infographic_flow" (NOT a map).
- FIRST scene = infographic_title (intro), LAST = infographic_title (outro).
- Numbers are WHOLE INTEGERS in base units: 1480000 not 1.48; 65000 not "65k".
  Units (€, %, Mio) go in label/suffix, never in the number.
- GROUNDING (critical): every figure/year/place/quote in remotion_data MUST be stated in
  THIS scene's narration text. Never invent data, never guess. If it isn't in the text,
  use stock_video — a graphic with invented data is worse than b-roll. "accent" = hex or omit.
- Don't repeat the same visual twice across the video; each on_screen must be distinct.
- HOOK (first 10-15s): the strongest, most surprising visual + the headline number, with
  visual CONTRAST (e.g. an empty doctor's office with the big number over it). This decides
  whether viewers stay. Make scene 1 land the core claim instantly.
- LOCALE: this is a "{lang}" documentary. Footage/places must fit the audience — prefer
  German/European locations, signage and people; avoid obviously foreign (US/Asia) footage
  unless the narration is about that place. Add the country to queries when it helps.
- Insert an "infographic_title" CHAPTER card at each major section change (re-hooks attention).
- Keep KEY numbers on screen: when a stock/image scene states a statistic, fill "text_overlay".
- Do NOT place more than TWO infographic scenes back-to-back — break them with stock/image.

Return ONLY a JSON array of scenes. No markdown.

Script:
{script}"""

    # Ретраи: scene plan — большой JSON, LLM иногда косячит синтаксис. Толерантный
    # парсер + до 3 свежих генераций, чтобы единичный слип не валил весь прогон.
    scenes = None
    last_err = None
    for attempt in range(3):
        response = await call_llm(
            prompt=prompt,
            model=model_config["primary"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
        )
        try:
            parsed = _extract_scenes_json(response)
            if isinstance(parsed, list) and parsed:
                scenes = parsed
                break
            raise ValueError("scene plan пустой или не список")
        except Exception as e:
            last_err = e
            logger.warning(f"scene plan parse попытка {attempt+1}/3 не удалась: {e}")
    if not scenes:
        raise RuntimeError(f"Scene plan JSON parse error после 3 попыток: {last_err}")

    scenes = _normalize_scene_types(scenes)
    n_info = sum(1 for s in scenes if s.get("visual_type", "stock") != "stock")
    logger.info(f"Scene plan: {len(scenes)} scenes ({n_info} infographic, "
                f"{len(scenes) - n_info} stock) for {total_duration:.0f}s video")
    return scenes


# intent-first медиум → внутренний visual_type (downstream работает на visual_type)
_MEDIUM_TO_VISUAL_TYPE = {
    "stock_video": "stock",
    "image": "image",
    "doodle": "doodle",
    "concept": "remotion_concept",
    "infographic_counter": "remotion_counter",
    "infographic_chart": "remotion_chart",
    "infographic_split": "remotion_split",
    "infographic_title": "remotion_title",
    "infographic_map": "remotion_map",
    "infographic_flow": "remotion_flow",
    "infographic_stat": "remotion_stat",
    "infographic_timeline": "remotion_timeline",
    "infographic_ranked": "remotion_ranked",
    "infographic_table": "remotion_table",
    "infographic_quote": "remotion_quote",
}

_VALID_VISUAL_TYPES = {
    "stock", "image", "doodle", "remotion_counter", "remotion_chart",
    "remotion_split", "remotion_title", "remotion_map", "remotion_concept",
    "remotion_flow", "remotion_stat", "remotion_timeline", "remotion_ranked",
    "remotion_table", "remotion_quote",
}

# data-инфографика (счётчики/графики), которая «утомляет глаз» подряд.
# remotion_title (титры/главы) НЕ считаем — они сами по себе визуальная пауза.
_DATA_INFOGRAPHIC = {"remotion_counter", "remotion_chart", "remotion_split", "remotion_map"}

_DEFAULT_QUERIES = ["documentary footage", "abstract background"]
_QUERY_STOP = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "and", "or",
               "as", "is", "are", "that", "this", "showing", "illustrating", "depicting",
               "infographic", "graphic", "chart", "scene", "shot", "view", "image"}


def _derive_queries(on_screen: str) -> list[str]:
    """Из описания сцены (on_screen) делает 2-3 конкретных англ. стоковых запроса.
    Нужно когда инфографику пришлось перевести в сток, а реальных запросов нет."""
    import re
    words = [w for w in re.sub(r"[^\w\s]", " ", (on_screen or "").lower()).split()
             if w not in _QUERY_STOP and len(w) > 2]
    if not words:
        return []
    core = " ".join(words[:5])
    out = [core]
    if "german" not in core and "germany" not in core:
        out.append(core + " germany")
    if len(words) > 3:
        out.append(" ".join(words[:3]))
    # дедуп с сохранением порядка
    seen, uniq = set(), []
    for q in out:
        if q and q not in seen:
            seen.add(q); uniq.append(q)
    return uniq[:3]


def _normalize_scene_types(scenes: list[dict]) -> list[dict]:
    """Map medium → visual_type; затем grounding-валидатор (remotion_validate):
    каждое число/место/год/цитата должно быть в тексте сцены, иначе сцена
    деградирует в сток. Все per-type правила — в validate_remotion_data."""
    from backend.pipeline.remotion_validate import validate_remotion_data
    for s in scenes:
        # intent-first планы несут "medium"; маппим. Fallback на явный visual_type.
        medium = (s.get("medium") or "").strip()
        vt = _MEDIUM_TO_VISUAL_TYPE.get(medium) or (s.get("visual_type") or "stock").strip()
        if vt not in _VALID_VISUAL_TYPES:
            vt = "stock"
        s["visual_type"] = vt

        if vt.startswith("remotion_"):
            data = s.get("remotion_data")
            if isinstance(data, dict):
                _fix_million_floats(data)  # 1.48 "Mio" → 1480000 ДО grounding
            new_vt, new_data, viol = validate_remotion_data(s)
            s["visual_type"] = new_vt
            if new_vt.startswith("remotion_") and new_data is not None:
                s["remotion_data"] = new_data
            else:
                s.pop("remotion_data", None)  # деградировало в сток
            if viol:
                logger.info(f"scene viz: {vt}→{new_vt} ({'; '.join(viol[:2])})")
        else:
            s.pop("remotion_data", None)  # image/stock не несут remotion_data

        q = s.get("queries")
        if not q or q == _DEFAULT_QUERIES:
            s["queries"] = _derive_queries(s.get("on_screen") or "") or [
                "german city documentary", "people working germany"]
    return scenes


def _coerce_num(v) -> float | int | None:
    """LLM кладёт числа и как int, и как '1,9 Mrd', и как None — приводим или None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v if v == v and abs(v) != float("inf") else None  # NaN/inf → None
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.,\-]", "", v).replace(",", ".")
        # '1.480.000' → точки-разделители тысяч: оставляем последнюю как десятичную
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            n = float(cleaned)
            return int(n) if n.is_integer() else n
        except ValueError:
            return None
    return None


def _fix_million_floats(data: dict) -> None:
    """Scale 'millions as decimal' to base unit: leftValue 1.48 + label 'Mio' → 1480000.

    Only fires when a value is a small float AND its label/title says Mio/Million —
    so genuine fractional values (rare) and percentages are left alone.
    """
    for vkey, lkey in (("to", "label"), ("from", "label"),
                       ("leftValue", "leftLabel"), ("rightValue", "rightLabel")):
        v = data.get(vkey)
        ctx = f"{data.get(lkey, '')} {data.get('suffix', '')} {data.get('title', '')}".lower()
        if isinstance(v, float) and 0 < abs(v) < 1000 and ("mio" in ctx or "million" in ctx):
            data[vkey] = int(round(v * 1_000_000))


def _render_infographic(scene: dict, scene_duration: float, clip_path: Path) -> bool:
    """Render a Remotion infographic for this scene → video-only mp4.

    Maps visual_type/remotion_data to remotion_render.render_for_scene, then strips
    Remotion's silent audio track so the clip matches stock clips (video-only).
    """
    import subprocess, tempfile
    from backend.pipeline.remotion_render import render_for_scene

    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "remotion.mp4"
        ok = render_for_scene({
            "type": scene.get("visual_type", ""),
            "remotion_data": scene.get("remotion_data") or {},
            "duration": scene_duration,
        }, raw)
        if not ok or not raw.exists():
            return False
        try:
            # ПЕРЕ-КОДИРУЕМ в чистый H.264 (а не -c copy): remux копией иногда давал
            # поток, который DaVinci помечает offline/красным. libx264+yuv420p читается
            # всегда. Чуть медленнее, зато клип не «теряется».
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw), "-map", "0:v:0",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-an", str(clip_path)],
                check=True, capture_output=True, timeout=180)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    return clip_path.exists() and clip_path.stat().st_size > 10000


def _has_visual_content(clip_path: Path) -> bool:
    """True, если в клипе есть РЕАЛЬНОЕ изображение, а не пустой однотонный кадр
    (белый/чёрный экран). Берём до 20 кадров через ffmpeg signalstats: если ни на одном
    разброс яркости (YMAX-YMIN) не дотягивает до порога — кадр пустой → False.
    Fail-open: при любой ошибке анализа возвращаем True (лучше пропустить, чем зарубить
    валидный клип). Размер файла >10КБ не ловит белый экран — это ловит."""
    import subprocess, re as _re
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(clip_path),
             "-vf", "signalstats,metadata=print", "-frames:v", "20", "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=40)
        out = r.stdout + r.stderr
        ymins = [int(m) for m in _re.findall(r"YMIN=(\d+)", out)]
        ymaxs = [int(m) for m in _re.findall(r"YMAX=(\d+)", out)]
        if not ymins or not ymaxs:
            return True  # не проанализировали — не блокируем
        return max(hi - lo for lo, hi in zip(ymins, ymaxs)) >= 24
    except Exception:
        return True


def _download_image(scene: dict, duration: float, clip_path: Path) -> bool:
    """Real still photo (archival / portrait / document / map) → Ken Burns motion clip.

    Sources: Wikipedia/Wikimedia (free, great for historical) + Pexels photo.
    """
    import os
    import tempfile
    import urllib.request
    from backend.pipeline.image_gen import apply_ken_burns
    from backend.visual_router import search_wikipedia_image, search_pexels_photo, UA

    pexels = os.environ.get("PEXELS_API_KEY", "")
    candidates = []
    for q in (scene.get("queries") or [])[:3]:
        candidates += search_wikipedia_image(q, 3)
        if pexels:
            candidates += search_pexels_photo(q, pexels, 3)

    for c in candidates:
        url = c.get("url")
        if not url:
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                img = Path(td) / "photo"
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r, open(img, "wb") as f:
                    f.write(r.read())
                apply_ken_burns(img, clip_path, duration)
            if clip_path.exists() and clip_path.stat().st_size > 10000:
                return True
        except Exception:
            continue
    return False


def _ensure_slot_length(clip_path: Path, slot_sec: float) -> None:
    """Клип короче своего слота в таймлайне → в DaVinci остаток слота = ДЫРА
    (asset-clip не может быть длиннее исходного медиа). Зацикливаем клип до длины
    слота. Без лупа сток 9с в слоте 15с давал 6с пустого кадра."""
    import subprocess, tempfile
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
            capture_output=True, text=True, timeout=30)
        media = float(r.stdout.strip())
        if media <= 0.2 or media >= slot_sec - 0.25:
            return
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "looped.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(clip_path),
                 "-t", f"{slot_sec + 0.2:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "21", "-pix_fmt", "yuv420p", "-an", str(out)],
                check=True, capture_output=True, timeout=180)
            if out.exists() and out.stat().st_size > 10000:
                subprocess.run(["cp", str(out), str(clip_path)], check=True, timeout=30)
    except Exception as e:
        logger.warning(f"loop-to-slot пропущен для {clip_path.name}: {e}")


BURN_OVERLAYS = True  # запекать text_overlay (ключевые числа) на сток/image-клипы
_OVERLAY_FONTS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _burn_overlay(clip_path: Path, text: str) -> None:
    """Запекает короткий lower-third (тёмная плашка + белый жирный текст) на клип.

    Держит ключевое число на экране поверх b-roll = доверие + удержание.
    Любая ошибка — тихо пропускаем (клип остаётся без оверлея).
    """
    import subprocess
    import tempfile
    text = (text or "").strip()
    if not text or not BURN_OVERLAYS or not clip_path.exists():
        return
    font = next((f for f in _OVERLAY_FONTS if Path(f).exists()), None)
    try:
        with tempfile.TemporaryDirectory() as td:
            tf = Path(td) / "overlay.txt"
            tf.write_text(text, encoding="utf-8")
            out = Path(td) / "out.mp4"
            draw = (
                "drawbox=x=0:y=ih-150:w=iw:h=150:color=black@0.55:t=fill,"
                f"drawtext=textfile={tf}:fontcolor=white:fontsize=58:x=70:y=h-108"
                + (f":fontfile={font}" if font else "")
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(clip_path), "-vf", draw,
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-an", str(out)],
                check=True, capture_output=True, timeout=120)
            if out.exists() and out.stat().st_size > 10000:
                subprocess.run(["cp", str(out), str(clip_path)], check=True, timeout=30)
    except Exception:
        pass


# --- Shot splitting: turn semantic scenes into ~6s shots for visual variety ---
SHOT_TARGET_SEC = 6.0       # цель длины одного кадра
SHOT_MIN_SEC = 3.5          # короче этого не режем (без огрызков-вспышек)
SHOT_SPLIT_THRESHOLD = 10.0  # сток короче порога оставляем одним кадром
MAX_INFOGRAPHIC_RUN = 2      # не больше N инфографик подряд → дальше b-roll

# Темп под смысл: на data/напряжённых сценах режем чаще, на спокойных даём дышать.
_MOOD_TARGET = {"dramatic": 5.0, "tense": 5.0, "dark": 5.5,
                "neutral": 6.0, "uplifting": 7.0, "calm": 7.5}


def _target_for_mood(mood: str) -> float:
    return _MOOD_TARGET.get((mood or "neutral").strip().lower(), SHOT_TARGET_SEC)

# Сколько секунд инфографика держится на экране, прежде чем уступить b-roll.
# Число/титр отыгрывает ~6с, график дольше (его надо успеть прочитать).
_INFOGRAPHIC_CAP = {
    "remotion_counter": 6.0,
    "remotion_title": 6.0,
    "remotion_split": 7.0,
    "remotion_map": 7.0,
    "remotion_chart": 9.0,
    "image": 7.0,   # фото с Ken Burns держится ~7с, дальше b-roll
}


SNAP_TOL = 1.8  # на сколько секунд можно сдвинуть кат к естественной паузе голоса


def _snap(t: float, cut_points: list, tol: float = SNAP_TOL) -> float:
    """Ближайшая точка реза к t (если в пределах tol), иначе сам t."""
    best, best_d = t, tol
    for cp in cut_points:
        d = abs(cp - t)
        if d <= best_d:
            best, best_d = cp, d
    return best


def _even_split(start: float, end: float, target: float = SHOT_TARGET_SEC,
                cut_points: list = None) -> list[tuple[float, float]]:
    """Делит [start,end] на куски ~target. Если есть cut_points (паузы голоса) —
    притягивает каты к ним (монтаж по голосу). Сегменты не короче SHOT_MIN_SEC."""
    dur = end - start
    n = max(1, round(dur / target))
    while n > 1 and dur / n < SHOT_MIN_SEC:
        n -= 1
    times = [start + dur * k / n for k in range(1, n)]
    if cut_points:
        times = [_snap(t, cut_points) for t in times]
    # санитизация: по возрастанию, каждый сегмент >= SHOT_MIN_SEC
    clean, prev = [], start
    for t in sorted(times):
        if t - prev >= SHOT_MIN_SEC and end - t >= SHOT_MIN_SEC:
            clean.append(t)
            prev = t
    bounds = [start] + clean + [end]
    return [(round(bounds[k], 3), round(bounds[k + 1], 3)) for k in range(len(bounds) - 1)]


def _stock_shot(scene: dict, start: float, end: float, query_rotation: int) -> dict:
    """Сток-шот: своя пара start/end + повёрнутый список запросов (другой кадр)."""
    sh = dict(scene)
    sh["start"], sh["end"] = start, end
    sh["visual_type"] = "stock"
    sh.pop("remotion_data", None)
    q = scene.get("queries") or []
    if q:
        r = query_rotation % len(q)
        sh["queries"] = q[r:] + q[:r]
    return sh


def _merge_short_scenes(scene_plan: list[dict], min_sec: float = SHOT_MIN_SEC) -> list[dict]:
    """Сливает крошечные сцены с соседями — лекарство от мельтешения.

    Scene planning раскадровывает по смыслу сценария («монтаж образов»), а
    реальная озвучка проговаривает кусок быстро: видели 15 сцен на 13 секунд
    (слоты по 0.2-1.1с) — на таймлайне это шквал клипов-вспышек. Зритель
    в основном слушает; видеоряду достаточно передавать настроение крупными
    планами 4-10с, а не иллюстрировать каждую фразу.

    Визуал слитого куска — от самой длинной составляющей (доминирующей),
    тексты конкатенируются (alignment по ним уже отработал).
    """
    if not scene_plan:
        return scene_plan

    def _dur(s: dict) -> float:
        return float(s.get("end", 0) or 0) - float(s.get("start", 0) or 0)

    def _merge(a: dict, b: dict) -> dict:
        dominant = b if _dur(b) > _dur(a) else a
        m = dict(dominant)
        m["start"] = a.get("start", 0)
        m["end"] = b.get("end", 0)
        m["text"] = (str(a.get("text", "")) + " " + str(b.get("text", ""))).strip()
        if not m.get("text_overlay"):
            m["text_overlay"] = a.get("text_overlay") or b.get("text_overlay") or ""
        return m

    out = [dict(scene_plan[0])]
    for s in scene_plan[1:]:
        prev = out[-1]
        # предыдущий кусок ещё крошка → доращиваем безусловно;
        # текущая сцена крошка → подтягиваем к prev, пока итог не раздулся
        if _dur(prev) < min_sec or (_dur(s) < min_sec and _dur(prev) + _dur(s) <= 10.0):
            out[-1] = _merge(prev, s)
        else:
            out.append(dict(s))
    # хвостовая крошка липнет к предпоследнему куску
    if len(out) > 1 and _dur(out[-1]) < min_sec:
        out[-2] = _merge(out[-2], out[-1])
        out.pop()
    if len(out) != len(scene_plan):
        logger.info(f"merge коротких сцен: {len(scene_plan)} → {len(out)}")
    return out


def split_scenes(scene_plan: list[dict]) -> list[dict]:
    """Expand semantic scenes into a finer shot list.

    - stock scene → ~6s shots, each with a different query (varied b-roll)
    - infographic scene → one capped infographic shot, remainder of the beat as
      stock b-roll (so a number never sits static for 10s)
    """
    shots: list[dict] = []
    for scene in scene_plan:
        start = float(scene.get("start", 0) or 0)
        end = float(scene.get("end", 0) or 0)
        vt = scene.get("visual_type", "stock")
        if end <= start:
            shots.append(scene)
            continue

        target = _target_for_mood(scene.get("mood"))
        cuts = scene.get("cut_points")  # естественные паузы голоса (из align_scenes)
        if vt == "stock":
            if (end - start) <= SHOT_SPLIT_THRESHOLD:
                shots.append(scene)  # короткая сцена — один кадр
            else:
                for k, (a, b) in enumerate(_even_split(start, end, target, cuts)):
                    shots.append(_stock_shot(scene, a, b, k))
            continue

        # Infographic: hold for its natural cap, then b-roll the rest of the beat.
        cap = _INFOGRAPHIC_CAP.get(vt, SHOT_TARGET_SEC)
        if (end - start) <= cap + SHOT_MIN_SEC:
            shots.append(scene)  # short beat — infographic holds the whole thing
            continue
        info = dict(scene)
        info["start"], info["end"] = start, round(start + cap, 3)
        shots.append(info)
        for k, (a, b) in enumerate(_even_split(round(start + cap, 3), end, target, cuts)):
            shots.append(_stock_shot(scene, a, b, k))
    return _enforce_variety(shots)


def _enforce_variety(shots: list[dict], max_run: int = MAX_INFOGRAPHIC_RUN) -> list[dict]:
    """Не больше max_run инфографик подряд — лишние превращаем в сток b-roll."""
    run = 0
    for sh in shots:
        vt = sh.get("visual_type", "stock")
        if vt in _DATA_INFOGRAPHIC:
            run += 1
            if run > max_run:
                sh["visual_type"] = "stock"  # глаз устал от графиков → реальный кадр
                sh.pop("remotion_data", None)
                q = sh.get("queries")
                if not q or q == _DEFAULT_QUERIES:
                    sh["queries"] = _derive_queries(sh.get("on_screen") or "") or [
                        "german city documentary", "people working germany"]
        elif vt == "remotion_title":
            continue  # титр — тоже графика: не считаем, но и НЕ сбрасываем серию
        else:
            run = 0  # реальный кадр (сток/фото) — глаз отдохнул, серия сброшена
    return shots


async def download_clips(
    scene_plan: list[dict],
    output_dir: Path,
    progress_cb=None,
    topic: str = "",
) -> list[dict]:
    """
    Download stock clips for each scene.
    
    Searches multiple sources, scores clips for relevance,
    downloads best matches.
    
    Args:
        scene_plan: List of scenes with search queries
        output_dir: Directory to save clips
    
    Returns:
        List of clip metadata dicts
    """
    from backend.stock.multi import MultiStockClient

    output_dir.mkdir(parents=True, exist_ok=True)
    client = MultiStockClient()
    clip_map = []
    # Tracks which clip_map indices were recently used as reuse fallback.
    # Prevents the same clip from appearing within a window of 8 shots.
    recent_reuse: deque[int] = deque(maxlen=8)

    # Split long scenes into ~6s shots for visual variety; cap each infographic's
    # display time and fill the rest of the beat with stock b-roll.
    scene_plan = _merge_short_scenes(scene_plan)
    shots = split_scenes(scene_plan)
    logger.info(f"Shot list: {len(scene_plan)} scenes → {len(shots)} shots")

    # Unified-режим: для doodle-сцен заранее одним батчем генерим промпты (концепт→
    # конкретный объект, наша анти-абстракция логика), чтобы не дёргать LLM на каждую.
    doodle_prompt_for: dict[int, str] = {}
    doodle_idx = [i for i, s in enumerate(shots) if s.get("visual_type") == "doodle"]
    if doodle_idx:
        try:
            from backend.pipeline.stick_figure import generate_doodle_prompts
            dprompts = await generate_doodle_prompts([shots[i] for i in doodle_idx], topic)
            doodle_prompt_for = {i: dprompts[k] for k, i in enumerate(doodle_idx) if k < len(dprompts)}
            logger.info(f"doodle: промпты на {len(doodle_prompt_for)} сцен")
        except Exception as e:
            logger.warning(f"doodle prompts failed ({e}) → эти сцены уйдут в сток-фолбэк")

    # Слоты считаем заранее (зависят от старта следующего шота) — нужны и в
    # параллельном проходе, и в reuse-проходе.
    slot_secs: list[float] = []
    for i, scene in enumerate(shots):
        sd = scene.get("end", 0) - scene.get("start", 0)
        if i + 1 < len(shots):
            ss = max(sd, float(shots[i + 1].get("start", 0)) - float(scene.get("start", 0)))
        else:
            ss = sd + 3.0
        if ss > 25.0:
            logger.warning(f"Shot {i+1}: slot {ss:.0f}s > 25s — обрезаю (битые тайминги alignment?)")
            ss = max(sd, 25.0)
        slot_secs.append(ss)

    total = len(shots)
    # Конкуренция по классам ресурсов (8 vCPU / 8 GB): рендеры (chromium, RAM) — 2,
    # ffmpeg (CPU) — 4, FAL (картинки/дудлы) — 4, сток-скачивание — 3 (чтобы не ловить
    # throttle с дата-центрового IP). Семафоры режут реальную нагрузку; gather
    # запускает все шоты, но выполняются они порциями.
    sem_render = asyncio.Semaphore(2)
    sem_ffmpeg = asyncio.Semaphore(4)
    sem_fal = asyncio.Semaphore(4)
    sem_stock = asyncio.Semaphore(3)
    done_count = 0

    async def _ff(fn, *a):
        async with sem_ffmpeg:
            return await asyncio.to_thread(fn, *a)

    async def _acquire_shot(i: int, scene: dict):
        """Независимое получение клипа для шота (БЕЗ reuse-фолбэка — он зависит от
        других клипов и идёт вторым проходом). Возвращает dict для clip_map или None."""
        nonlocal done_count
        queries = scene.get("queries", [])
        scene_duration = scene.get("end", 0) - scene.get("start", 0)
        slot_sec = slot_secs[i]
        visual_type = scene.get("visual_type", "stock")
        clip_path = output_dir / f"clip_{i:03d}.mp4"
        base = {
            "scene_index": i, "path": str(clip_path), "slot_sec": slot_sec,
            "scene_start": scene.get("start", 0), "scene_end": scene.get("end", 0),
            "mood": scene.get("mood", "neutral"),
            "scene_text": scene.get("on_screen") or scene.get("text", ""),
            "text_overlay": scene.get("text_overlay", ""),
        }
        try:
            # Infographic → Remotion (не сток, не Flux). Сбой → сток-фолбэк ниже.
            if visual_type.startswith("remotion_"):
                async with sem_render:
                    ok = await asyncio.to_thread(_render_infographic, scene, scene_duration, clip_path)
                if ok:
                    await _ff(_ensure_slot_length, clip_path, slot_sec)
                    logger.info(f"Scene {i+1}/{total}: rendered {visual_type} ({scene_duration:.0f}s)")
                    return {**base, "query": visual_type, "source": "remotion", "duration": scene_duration}
                logger.warning(f"Scene {i+1}: {visual_type} render failed → stock fallback")

            # Doodle → набросок (концепт/метафора). Сбой → сток/Flux/reuse.
            if visual_type == "doodle":
                from backend.pipeline.stick_figure import render_doodle
                prompt = doodle_prompt_for.get(i, "")
                async with sem_fal:
                    rok = await render_doodle(prompt, slot_sec, clip_path)
                if rok and await asyncio.to_thread(_has_visual_content, clip_path):
                    await _ff(_ensure_slot_length, clip_path, slot_sec)
                    await _ff(_burn_overlay, clip_path, scene.get("text_overlay", ""))
                    logger.info(f"Scene {i+1}/{total}: doodle ({scene_duration:.0f}s)")
                    return {**base, "query": "doodle", "source": "doodle",
                            "duration": scene_duration, "scene_text": prompt or base["scene_text"]}
                logger.warning(f"Scene {i+1}: doodle render failed/пустой кадр → stock/flux fallback")

            # Image → реальное фото + Ken Burns. Сбой → сток, потом Flux.
            if visual_type == "image":
                iok = await asyncio.to_thread(_download_image, scene, scene_duration, clip_path)
                if iok and await asyncio.to_thread(_has_visual_content, clip_path):
                    await _ff(_ensure_slot_length, clip_path, slot_sec)
                    await _ff(_burn_overlay, clip_path, scene.get("text_overlay", ""))
                    logger.info(f"Scene {i+1}/{total}: image+KenBurns ({scene_duration:.0f}s)")
                    return {**base, "query": (queries[0] if queries else "image"),
                            "source": "image", "duration": scene_duration}
                logger.warning(f"Scene {i+1}: image fetch failed → stock fallback")

            # Сток-видео по очереди запросов.
            logger.info(f"Scene {i+1}/{total}: {scene_duration:.0f}s stock, queries={queries[:2]}...")
            for query in queries:
                async with sem_stock:
                    result = await client.search_and_download(
                        query=query, min_duration=max(5, scene_duration * 0.6),
                        output_path=clip_path,
                        scene_text=scene.get("on_screen") or scene.get("text", ""))
                if result:
                    await _ff(_ensure_slot_length, clip_path, slot_sec)
                    await _ff(_burn_overlay, clip_path, scene.get("text_overlay", ""))
                    return {**base, "query": query, "source": result.get("source", "unknown"),
                            "duration": result.get("duration", scene_duration)}

            # Фолбэк 1: Flux-картинка + Ken Burns (ТОЛЬКО stock/image; data-сцены — нет).
            if visual_type in ("stock", "image"):
                from backend.pipeline.image_gen import generate_clip_fallback
                async with sem_fal:
                    fb = await generate_clip_fallback(
                        scene_text=scene.get("text", ""), topic=scene.get("text", "")[:200],
                        lang="en", duration=scene_duration, output_path=clip_path)
                if fb:
                    logger.info(f"Scene {i+1}: used AI image + Ken Burns")
                    return {**base, "query": "ai_generated", "source": "fal_flux", "duration": scene_duration}
        except Exception as e:
            logger.warning(f"Scene {i+1}: acquire error ({e}) → reuse-фолбэк")
        finally:
            done_count += 1
            if progress_cb:
                try: progress_cb(f"Клипы: {done_count}/{total}")
                except Exception: pass
        return None

    # Проход 1 — параллельное независимое получение клипов (порядок результатов
    # сохраняется gather'ом).
    results = await asyncio.gather(*[_acquire_shot(i, shots[i]) for i in range(len(shots))])

    # Проход 2 — ПОСЛЕДОВАТЕЛЬНЫЙ reuse-фолбэк для пустых слотов (зависит от уже
    # полученных клипов; идёт строго в порядке шотов — детерминизм + recent_reuse).
    clip_map = []
    recent_reuse = deque(maxlen=8)
    for i in range(len(shots)):
        r = results[i]
        if r is not None:
            clip_map.append(r)
            continue
        scene = shots[i]
        slot_sec = slot_secs[i]
        clip_path = output_dir / f"clip_{i:03d}.mp4"
        if clip_map:
            import shutil
            available = [k for k in range(len(clip_map)) if k not in recent_reuse]
            if not available:
                available = list(range(len(clip_map)))
            reuse_idx = available[i % len(available)]
            recent_reuse.append(reuse_idx)
            shutil.copy2(clip_map[reuse_idx]["path"], clip_path)
            await asyncio.to_thread(_ensure_slot_length, clip_path, slot_sec)
            clip_map.append({
                "scene_index": i, "path": str(clip_path), "query": "reuse", "source": "reuse",
                "duration": clip_map[reuse_idx]["duration"], "slot_sec": slot_sec,
                "scene_start": scene.get("start", 0), "scene_end": scene.get("end", 0),
                "mood": scene.get("mood", "neutral"),
                "scene_text": scene.get("on_screen") or scene.get("text", ""),
                "text_overlay": scene.get("text_overlay", ""),
            })
            logger.warning(f"Scene {i+1}: no clips found, reusing scene {reuse_idx+1}")
        else:
            logger.warning(f"Scene {i+1}: нет клипа и нечего переиспользовать — пропуск")
    
    # fcpxml читает search_query для QA-flags/motion-notes — зеркалим из query
    for c in clip_map:
        c["search_query"] = c.get("query", "")
    logger.info(f"Downloaded {len(clip_map)} clips for {len(scene_plan)} scenes")
    return clip_map
