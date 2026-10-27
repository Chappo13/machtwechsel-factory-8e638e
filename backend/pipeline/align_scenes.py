"""
Scene timing alignment via real voiceover.

После TTS первичный scene_plan имеет ПРЕДПОЛОЖИТЕЛЬНЫЕ тайминги (LLM прикинул).
Этот модуль:
  1. Прогоняет voice.mp3 через Deepgram → получает word-level timestamps
  2. Матчит текст каждой сцены к потоку слов
  3. Возвращает scene_plan с РЕАЛЬНЫМИ start/end по фактической озвучке

Это позволяет:
  - Подобрать клипы под реальные тайминги (не съезжают)
  - Перегенерировать FCPXML после ручной правки голоса
"""

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# Deepgram language codes (Deepgram использует ISO 639-1)
DG_LANG_MAP = {"de": "de", "es": "es", "en": "en", "pl": "pl", "ru": "ru", "vi": "vi"}

# nova-2 НЕ поддерживает вьетнамский → для vi принудительно nova-3, иначе тихий
# плохой scene-sync. nova-3 покрывает и de/es/en, но дефолт не трогаем для совместимости.
DG_NOVA3_LANGS = {"vi"}


def _normalize(s: str) -> str:
    """Strip punctuation, lower, collapse whitespace, NFD-fold."""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize(s: str) -> list[str]:
    return _normalize(s).split()


def _alpha_head(tokens: list[str], n: int) -> list[str]:
    """Первый непрерывный отрезок из n НЕ-цифровых токенов. Скрипт хранит «41%», а
    Deepgram пишет числа словами («cuarenta y uno») → цифровой head никогда не
    сматчится. Берём текстовую фразу (после числа), которая есть и в аудио."""
    run: list[str] = []
    for t in tokens:
        if t.isdigit():
            run = []
            continue
        run.append(t)
        if len(run) == n:
            return run
    return tokens[:n]


async def transcribe_with_words(
    audio_path: Path, lang: str, model: str = "nova-2"
) -> dict:
    """Transcribe audio via Deepgram with word-level timestamps.

    Returns dict with 'words' (list of {word, start, end}) and 'transcript'.
    """
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set")

    dg_lang = DG_LANG_MAP.get(lang, lang)
    if lang in DG_NOVA3_LANGS:
        model = "nova-3"  # vi не поддерживается в nova-2
    params = {
        "model": model,
        "language": dg_lang,
        "punctuate": "true",
        "utterances": "false",
        "smart_format": "false",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/mpeg",
    }

    audio_bytes = audio_path.read_bytes()
    logger.info(f"Deepgram: transcribing {audio_path.name} ({len(audio_bytes)} bytes, lang={dg_lang})")

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15, read=300, write=60, pool=300)) as client:
        resp = await client.post(DEEPGRAM_URL, params=params, content=audio_bytes, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Deepgram {resp.status_code}: {resp.text[:300]}")
        data = resp.json()

    try:
        alt = data["results"]["channels"][0]["alternatives"][0]
        words = alt.get("words", [])
        transcript = alt.get("transcript", "")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Deepgram unexpected response shape: {e}")

    logger.info(f"Deepgram: got {len(words)} words, transcript length={len(transcript)}")
    return {"words": words, "transcript": transcript}


def align_scenes_to_words(
    scene_plan: list[dict],
    words: list[dict],
    min_match_words: int = 3,
    audio_duration: float = 0.0,
) -> list[dict]:
    """Match each scene's narration to the word stream → assign real start/end.

    Args:
        scene_plan: list of scenes with at least 'text' field
        words: list of {word, start, end} from Deepgram
        min_match_words: minimum sequential word match to anchor scene start
        audio_duration: real voiceover length (ffprobe) — пол канвы. Deepgram
            иногда отдаёт слова только до середины (обрезанный/чанкнутый upload,
            хвост музыки-тишины) → без этого пола все сцены сжимались в первую
            половину, а видеоряд кончался чёрным хвостом.

    Returns:
        Updated scene_plan with 'start', 'end' from real timestamps.
        If matching fails — falls back to proportional distribution.
    """
    if not words:
        logger.warning("No words from Deepgram — using proportional fallback")
        return _fallback_proportional(scene_plan, audio_duration)

    # Канва = МАКСИМУМ из последнего слова Deepgram и реальной длины аудио.
    # Если DG обрезался на ~16 мин, words[-1].end не должен схлопнуть таймлайн.
    total_duration = max(words[-1]["end"] if words else 0.0, audio_duration or 0.0)
    norm_words = [_normalize(w.get("punctuated_word") or w["word"]) for w in words]

    # LLM-тайминги в плане — предположительные («90:00» при видео в 20 минут).
    # Снимаем ДО матчинга: иначе несматченные сцены сохраняют фантазийные
    # start/end, а _fill_gaps их пропускает («start уже есть») — отсюда
    # пересечения сцен до 620s в готовом видео.
    for s in scene_plan:
        s.pop("start", None)
        s.pop("end", None)

    # Проход 1: якорим СТАРТЫ сцен. Окно поиска ограничено — раньше head сцены
    # матчился с повторной фразой за сотни секунд вперёд и утаскивал cursor.
    anchors: dict[int, int] = {}  # scene index -> word index
    n_words = len(norm_words)
    cursor = 0
    for i, scene in enumerate(scene_plan):
        scene_tokens = _tokenize(scene.get("text", ""))
        if len(scene_tokens) < min_match_words:
            continue

        head = _alpha_head(scene_tokens, min_match_words)
        # Окно поиска: широкое, плюс пол ~15% всего потока — поздние сцены ищем
        # шире (числа/аббревиатуры сбивают якоря, и cursor отстаёт).
        reach = max(300, len(scene_tokens) * 3, int(n_words * 0.15))
        window_end = min(n_words - min_match_words + 1, cursor + reach)
        found_at = -1
        for j in range(cursor, window_end):
            if norm_words[j:j + min_match_words] == head:
                found_at = j
                break

        if found_at < 0 and min_match_words > 2:
            # Try loose match — first 2 non-numeric tokens
            head2 = _alpha_head(scene_tokens, 2)
            for j in range(cursor, max(cursor, min(window_end, n_words - 1))):
                if norm_words[j:j + 2] == head2:
                    found_at = j
                    break

        if found_at < 0:
            logger.warning(f"Scene {i+1}: no match for head '{' '.join(head)}' — skip")
            # НЕ пиним cursor: двигаем на оценку длины сцены, чтобы следующие сцены
            # искались около своей реальной позиции. Иначе блок промахов (числа,
            # аббревиатуры) запирает окно и весь хвост остаётся без якорей.
            cursor = min(max(n_words - 1, 0), cursor + max(len(scene_tokens), min_match_words))
            continue

        anchors[i] = found_at
        cursor = found_at + min_match_words

    if not anchors:
        logger.warning("Alignment matched 0 scenes — using proportional fallback")
        return _fallback_proportional(scene_plan, total_duration)

    # Проход 2: end сцены = длина её токенов, но НЕ ДАЛЬШЕ старта следующего
    # якоря. Токены сценария и распознанные Deepgram-слова расходятся (числа,
    # сокращения) — без клампа end уезжал на чужие слова.
    anchor_items = sorted(anchors.items())
    for k, (i, w_start) in enumerate(anchor_items):
        scene = scene_plan[i]
        tokens_len = len(_tokenize(scene.get("text", "")))
        next_w = anchor_items[k + 1][1] if k + 1 < len(anchor_items) else len(words)
        end_idx = min(w_start + tokens_len, next_w, len(words)) - 1
        end_idx = max(end_idx, w_start)  # минимум одно слово
        scene["start"] = round(words[w_start]["start"], 3)
        scene["end"] = round(words[end_idx]["end"], 3)

    # Fill gaps: if some scenes weren't matched, distribute их proportionally
    _fill_gaps(scene_plan, total_duration)
    _enforce_monotonic(scene_plan)
    # Хвост: последняя сцена должна доходить до конца канвы — иначе видеоряд
    # обрывается раньше голоса (если поздние якоря промахнулись).
    if scene_plan:
        last = scene_plan[-1]
        if "start" in last and last.get("end", 0.0) < total_duration:
            last["end"] = round(total_duration, 3)
    logger.info(f"Alignment: {len(anchors)}/{len(scene_plan)} scenes matched, "
                f"total duration {total_duration:.1f}s, "
                f"last scene end {scene_plan[-1].get('end', 0.0):.1f}s" if scene_plan else "")
    return scene_plan


def _probe_duration(audio_path: Path) -> float:
    """Длительность аудио через ffprobe; 0.0 если не удалось (тогда тайминги остаются как есть)."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception as e:
        logger.warning(f"ffprobe duration failed ({e}) → 0.0")
        return 0.0


def _fallback_proportional(scene_plan: list[dict], total_duration: float) -> list[dict]:
    """Когда matching полностью провалился — распределяем по char count сценариев."""
    if total_duration <= 0:
        # ничего не знаем, оставляем как есть
        return scene_plan
    total_chars = sum(len(s.get("text", "")) for s in scene_plan) or 1
    cursor = 0.0
    for s in scene_plan:
        frac = len(s.get("text", "")) / total_chars
        dur = total_duration * frac
        s["start"] = round(cursor, 3)
        s["end"] = round(cursor + dur, 3)
        cursor += dur
    return scene_plan


def _fill_gaps(scene_plan: list[dict], total_duration: float):
    """Для сцен без start/end — интерполировать между соседями.

    Группа подряд несматченных сцен делит интервал между якорями
    пропорционально длине текста (раньше каждая получала ВЕСЬ интервал —
    они полностью перекрывались).
    """
    n = len(scene_plan)
    i = 0
    while i < n:
        if "start" in scene_plan[i]:
            i += 1
            continue
        j = i
        while j < n and "start" not in scene_plan[j]:
            j += 1
        left_end = scene_plan[i - 1]["end"] if i > 0 and "end" in scene_plan[i - 1] else 0.0
        right_start = scene_plan[j]["start"] if j < n else total_duration
        span = max(right_start - left_end, 0.0)
        chars = [max(len(s.get("text", "")), 1) for s in scene_plan[i:j]]
        total_chars = sum(chars)
        cur = left_end
        for k, s in enumerate(scene_plan[i:j]):
            dur = span * chars[k] / total_chars
            s["start"] = round(cur, 3)
            s["end"] = round(cur + dur, 3)
            cur += dur
        i = j


def _enforce_monotonic(scene_plan: list[dict]):
    """Финальная страховка: тайминги строго неубывающие, без наложений."""
    prev_end = 0.0
    for s in scene_plan:
        if "start" not in s:
            continue
        if s["start"] < prev_end:
            s["start"] = round(prev_end, 3)
        if s.get("end", 0) < s["start"]:
            s["end"] = s["start"]
        prev_end = s["end"]


async def realign_scene_plan(
    voice_path: Path,
    scene_plan_path: Path,
    lang: str,
    output_path: Optional[Path] = None,
) -> Path:
    """High-level: load scene_plan, run Deepgram on voice, save aligned plan.

    Returns path to aligned scene_plan JSON.
    """
    scene_plan = json.loads(scene_plan_path.read_text(encoding="utf-8"))
    # Реальная длина голоса (ffprobe) — пол для канвы alignment, чтобы короткий
    # ответ Deepgram не обрезал видеоряд на середине.
    audio_dur = _probe_duration(voice_path)
    try:
        stt = await transcribe_with_words(voice_path, lang)
        aligned = align_scenes_to_words(scene_plan, stt["words"], audio_duration=audio_dur)
    except Exception as e:
        # Deepgram недоступен/упал — НЕ валим пайплайн: распределяем тайминги
        # пропорционально длине сценариев по реальной длительности голоса.
        logger.warning(f"Alignment через Deepgram не удался ({e}) → пропорциональный fallback")
        aligned = _fallback_proportional(scene_plan, audio_dur)
    out = output_path or scene_plan_path.with_name(scene_plan_path.stem + "_aligned.json")
    out.write_text(json.dumps(aligned, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Aligned plan saved to {out}")
    return out
