"""
YouTube metadata generation — 3 viral titles + description + tags.
Analyzes competitor metadata for SEO optimization.
"""

import json
import logging

from backend.config import get_model_config, get_channel_config
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)


async def generate_metadata(
    topic: str,
    script: str,
    lang: str,
    chapters: list[dict] | None = None,
) -> dict:
    """
    Generate YouTube metadata: 3 title options, description, tags.
    All titles follow proven viral patterns for the channel niche.

    Args:
        chapters: реальные главы из aligned scene plan: [{"time": "1:23",
            "hint": "TEIL 1 – ..."}]. LLM подписывает ТОЛЬКО эти времена —
            раньше он выдумывал тайминги («0:15…3:00, Weitere folgen»), и они
            уезжали в YouTube как ложные главы.

    Returns:
        Dict with titles (list of 3), titles_ru, description, tags
    """
    model_config = get_model_config("metadata")
    channel = get_channel_config(lang)
    niche = channel["niche"]

    lang_labels = {
        "de": ("Deutsch", "deutschen"),
        "es": ("Español", "spanischsprachigen"),
        "fr": ("Français", "francophone"),
    }
    lang_name, audience_adj = lang_labels.get(lang, ("English", "English-speaking"))

    chapters_block = ""
    if chapters:
        listing = "\n".join(f"   {c['time']} (hint: {c.get('hint', '')})" for c in chapters)
        chapters_block = f"""
6. "timestamps" — for EACH of these REAL chapter times write a short viewer-facing label in {lang_name} based on the script. Use EXACTLY these times, do NOT invent or add times:
{listing}
   Format: [{{"time": "0:00", "label": "..."}}]
   Do NOT include any timestamps inside "description" — they are inserted programmatically."""

    # Thumbnail-стиль зависит от канала: мультяшные (es/vi, stick_figure) — тёплый
    # flat-color cartoon как видеоряд; de/en (документалка) — фотореалистичный editorial.
    is_cartoon = (channel.get("visual_mode") == "stick_figure")
    if is_cartoon:
        thumb_block = f"""   The image_prompt is fed to an AI image model (Seedream) and must STOP the scroll, in a SIMPLE hand-drawn STICK-FIGURE doodle style (white round-headed characters, thin black-outline stick limbs, xkcd-like) — like the proven channel "AxenCool". Build each with ALL of:
   SIMPLE STICK-FIGURE SCENE (NOT a close-up of one face): ONE clear, instantly-readable scene with 1-3 white round-headed stick figures showing a STRONG, exaggerated emotion (scared / amazed / cozy / awkward / curious / moved) doing the one relatable thing THIS story is about, plus one or two simple props OR a contrasting element that hints at the stakes.
   MOOD VIA COLOR: pick the background color to match the topic — warm and bright for cozy/positive, dark and moody browns/blues for danger or tension. Flat saturated colors, strong contrast.
   TEXT HOOK BAKED IN: render the overlay_text as a big bold {lang_name} caption ACROSS THE TOP in a thick rounded hand-drawn sans-serif, bright YELLOW letters with a thick black outline. Spell it EXACTLY. 2-3 words, and NO other text anywhere else in the image.
   NO real/recognizable people, NO brand logos. 16:9, clean, bright and very readable on a small phone.
   OVERLAY_TEXT — the EXACT 2-3 punchy {lang_name} words on the image: a SHORT, curiosity-driven QUESTION or punch (e.g. the {lang_name} equivalent of "SURVIVED HOW?", "NO PRIVACY?", "WHY DO WE CRY?") — never the full title."""
    else:
        thumb_block = f"""   The image_prompt is fed to OpenAI GPT-Image and must produce a thumbnail that STOPS the scroll. Build each with ALL of:
   BRIGHT & EYE-CATCHING (never muted/dark): ultra-high contrast, vivid saturated colors, bright dramatic cinematic lighting, glossy premium look, ONE saturated accent color (red/gold/yellow) that pops on a tiny mobile screen.
   ONE STRIKING STORY-RELEVANT SUBJECT that creates a curiosity gap — pick the strongest for THIS story: a wealth-vs-ruin contrast, a before/after split of the SAME anonymous person divided by a bright crack, an anonymous person with a strong emotional face, OR one powerful symbolic object.
   TEXT HOOK BAKED INTO THE IMAGE: render the overlay_text as HUGE bold UPPERCASE {lang_name} letters — thick white/yellow letters with a contrasting (red/black) outline and drop shadow, very large and readable, in a clear/darker area. Spell it EXACTLY. 2-4 words.
   POLICY (or GPT-Image rejects it): NO real/named/recognizable people (a GENERIC anonymous figure), NO brand names/logos, NO graphic content → only symbolic/editorial. NO real person name and NO brand name in the image_prompt.
   16:9, photoreal editorial documentary style, sharp focus, clean and uncluttered.
   OVERLAY_TEXT — the EXACT 2-4 punchy {lang_name} words rendered on the image (a curiosity/stakes hook or the key number). Bold and dramatic."""

    prompt = f"""Create YouTube metadata for a {niche} {'cartoon curiosity' if is_cartoon else 'documentary'} video.

Topic: {topic}
Language: {lang_name}
Channel style: {channel.get('script_style', {}).get('tone', 'analytical')}

Generate:
1. "titles" — EXACTLY 3 viral title options in {lang_name}, in the warm-witty curiosity voice of channels like @AxenCool / @MackExplains7. Punchy, scroll-stopping, a real curiosity gap or a cheeky/surprising angle — NEVER dry or academic. Make people NEED to click:
   - Title 1: the core curiosity QUESTION, plain and irresistible (e.g. "¿Cuándo empezaron a fumar los humanos antiguos?")
   - Title 2: a surprising/edgy reveal that flips an assumption (not a dull "La verdad sobre…")
   - Title 3: a vivid, specific hook — a number, a "antes de X", or a "lo que nadie te cuenta" angle
   Each max 70 chars. Be provocative and fun, but never an outright lie.

2. "titles_ru" — Russian translations of all 3 titles (for review)

2b. "titles_ab" — for EACH title an A/B-testing assessment:
   {{"score": <0-100 expected CTR potential>, "why_ru": "<1 sentence IN RUSSIAN: для какой аудитории/подачи это название, когда его тестировать>"}}

3. "description" — YouTube description in {lang_name}, in a WARM, witty, conversational first-person voice (a smart friend telling you something wild) — the SAME tone as the script, NOT an academic summary:
   - Open with a SHORT punchy hook (1-2 sentences): a vivid image or a "you"-moment that pulls the viewer in. NEVER start with "¿Sabías que…?"; NEVER use "en este video" / "en este vídeo" / "descubro" / "te muestro" / "in this video".
   - Then 2-4 short sentences teasing the most intriguing bits WITHOUT lecturing — weave in at most 1-2 concrete facts as hooks, do NOT dump a list of names/dates.
   - End with a curiosity question or a soft "stay till the end" nudge.
   - After the nudge, add 2 CTA lines (on their own line each):
     Line 1: "👉 Suscríbete para no perderte el próximo — [thematic teaser e.g. 'el pasado tiene más secretos']"  (adapt to lang)
     Line 2: "👍 Dale like si esto te sorprendió — ayuda a que más gente lo descubra." (adapt to lang)
   - Keep it TIGHT (~4-7 short lines + 2 CTA lines). Punchy over poetic.
   - Relevant hashtags at the end (AFTER the CTAs).
   - NO timestamps (added programmatically from real scene timings)

3b. "description_ru" — Russian translation of the description (for the channel owner to understand).

3c. "pinned_comment" — A short PINNED AUTHOR COMMENT in {lang_name} (1-3 sentences). Post it right after publishing and pin it. Goal: spark discussion AND drive subscriptions. Formula:
   - Ask one engaging question about the most surprising fact from the video (makes people reply)
   - End with a soft subscribe nudge: "Si quieres más, suscríbete — subo cada semana 🙏" (adapt to lang)
   - Warm, conversational, NOT spammy. Max 3 sentences. NO emojis overload.

3d. "shorts_moments" — 3 best moments from this video to repurpose as YouTube Shorts (vertical 9:16, 30-90 sec). For each moment:
   - "start": estimated timestamp like "01:45"
   - "end": estimated timestamp like "02:50"
   - "duration_sec": integer seconds (must be 30-90)
   - "hook": the ONE punchy sentence that opens the Short (in {lang_name}) — must grab in 2 seconds
   - "why_ru": 1 sentence in Russian: why this specific moment works as a Short (surprising fact, visual payoff, emotional peak, etc.)
   - "overlay_text": 2-4 words in {lang_name} to overlay on screen (all caps, punchy)
   - "cut_note": one sentence in Russian: practical note for the editor (where to cut, what to keep, what transitions)
   Choose moments with: a clear visual payoff OR a shocking stat OR an emotional peak. Avoid intros/outros.

4. "tags" — 20 YouTube tags in {lang_name}: LEAD with high-volume BROAD curiosity/history terms people actually search (the kind that get recommended), then a few specific long-tail from the video. Favor viral/trending niche terms over narrow academic jargon.

5. "thumbnail_prompts" — 3 HIGH-CTR thumbnail concepts. Each: {{"concept": "<short RU description>", "image_prompt": "<English prompt>", "overlay_text": "<the EXACT 2-4 {lang_name} words rendered ON the image>"}}

{thumb_block}
{chapters_block}

Script (first 3000 chars):
{script[:3000]}

Return ONLY valid JSON:
{{"titles": ["...", "...", "..."], "titles_ru": ["...", "...", "..."], "titles_ab": [{{"score": 85, "why_ru": "..."}}], "description": "...", "description_ru": "...", "pinned_comment": "...", "shorts_moments": [{{"start": "01:45", "end": "02:50", "duration_sec": 65, "hook": "...", "why_ru": "...", "overlay_text": "...", "cut_note": "..."}}], "tags": ["..."], "thumbnail_prompts": [{{"concept": "...", "image_prompt": "...", "overlay_text": "..."}}], "timestamps": [{{"time": "0:00", "label": "..."}}]}}"""

    response = await call_llm(
        prompt=prompt,
        model=model_config["primary"],
        temperature=model_config.get("temperature", 0.8),
        max_tokens=model_config.get("max_tokens", 4000),
        fallback_model=model_config.get("fallback"),  # Gonka 524 → Gemini, иначе сборка падала на метаданных
    )

    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        metadata = json.loads(response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse metadata JSON: {e}")
        metadata = {
            "titles": [topic[:70]],
            "titles_ru": [topic[:70]],
            "description": topic,
            "tags": [],
            "thumbnail_prompts": [{
                "concept": topic[:80],
                "image_prompt": ("warm flat-color 2D cartoon thumbnail, 16:9, extreme close-up of a round-headed cartoon character with a strong emotional face, cozy saturated colors, warm lighting, space on one side for big bold text, no real people, no logos" if is_cartoon else "High-contrast editorial documentary thumbnail, 16:9, a faceless businessman in a dark suit under dramatic red rim lighting, a collapsing chart behind him, simple dark background with empty space on one side for text, no logos, no real people, cinematic"),
                "overlay_text": "",
            }],
        }

    # Ensure we always have lists
    if "titles" not in metadata or not isinstance(metadata["titles"], list):
        metadata["titles"] = [metadata.get("title", topic[:70])]
    if "titles_ru" not in metadata:
        metadata["titles_ru"] = metadata["titles"]
    if not isinstance(metadata.get("thumbnail_prompts"), list) or not metadata["thumbnail_prompts"]:
        metadata["thumbnail_prompts"] = [{
            "concept": topic[:80],
            "image_prompt": (f"warm flat-color 2D cartoon thumbnail about {topic}, 16:9, round-headed character with a strong emotion, bright saturated colors, space for big bold text" if is_cartoon else f"Documentary editorial thumbnail about {topic}, 16:9, dramatic lighting, no faces"),
            "overlay_text": "",
        }]

    # Блок TIMESTAMPS собирается программно из РЕАЛЬНЫХ времён aligned-плана.
    # Любые LLM-таймстампы из description вычищаются (он их выдумывал).
    if chapters:
        metadata["description"] = _inject_real_timestamps(
            str(metadata.get("description", "")), chapters,
            metadata.get("timestamps"))

    logger.info(f"Metadata: {len(metadata['titles'])} titles generated")
    return metadata


_LANG_NAMES = {"de": "German", "es": "Spanish", "en": "English", "vi": "Vietnamese"}


async def translate_metadata(src_meta: dict, src_lang: str, target_lang: str) -> dict:
    """Перевести ГОТОВЫЕ метаданные источника на целевой язык (для мульти-язык фичи).

    Зачем не generate_metadata: тот тянет get_channel_config(target_lang) →
    для de это finance-ниша + editorial-превью. Перевод сохраняет curiosity-тон,
    нишу и оптимизированные тайтлы источника, обходя конфиг канала, и стоит 1 дешёвый
    LLM-вызов. RU-переводы (titles_ru/description_ru) и concept остаются — смысл тот же;
    image_prompt язык-нейтрален (англ.). Переводим только то, что зритель видит на
    целевом языке: titles, description, tags, overlay_text."""
    src_name = _LANG_NAMES.get(src_lang, src_lang)
    tgt_name = _LANG_NAMES.get(target_lang, target_lang)
    cfg = get_model_config("translation")
    titles = [str(t) for t in (src_meta.get("titles") or [])]
    description = str(src_meta.get("description") or "")
    tags = [str(t) for t in (src_meta.get("tags") or [])]
    overlays = [str((tp or {}).get("overlay_text") or "")
                for tp in (src_meta.get("thumbnail_prompts") or [])]
    payload = {"titles": titles, "description": description, "tags": tags,
               "overlay_text": overlays}
    prompt = (
        f"Translate this YouTube metadata from {src_name} into {tgt_name}. "
        f"Keep the same viral, curiosity-driven, emotional tone. Tags must be natural "
        f"{tgt_name} SEO search terms (translate meaning, not literal). overlay_text are "
        f"the SHORT 2-4 word punchy hooks rendered on the thumbnail — keep them short and "
        f"punchy in {tgt_name}. Return ONLY valid JSON with EXACTLY these keys and the same "
        f"array lengths as input:\n"
        f'{{"titles": [...], "description": "...", "tags": [...], "overlay_text": [...]}}\n\n'
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    response = (await call_llm(
        prompt=prompt, model=cfg["primary"],
        temperature=cfg.get("temperature", 0.5), max_tokens=cfg.get("max_tokens", 4000),
        fallback_model=cfg.get("fallback"),
    )).strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        tr = json.loads(response)
    except json.JSONDecodeError as e:
        logger.error(f"translate_metadata: JSON не распарсен ({e}) — оставляю исходные метаданные")
        return dict(src_meta)
    # Собираем новый dict: переведённые видимые поля поверх исходных (RU/concept/ab/image_prompt сохраняем)
    out = dict(src_meta)
    if isinstance(tr.get("titles"), list) and tr["titles"]:
        out["titles"] = [str(t) for t in tr["titles"]]
    if isinstance(tr.get("description"), str) and tr["description"].strip():
        out["description"] = tr["description"].strip()
    if isinstance(tr.get("tags"), list) and tr["tags"]:
        out["tags"] = [str(t) for t in tr["tags"]]
    new_overlays = tr.get("overlay_text") if isinstance(tr.get("overlay_text"), list) else []
    tps = [dict(tp) for tp in (src_meta.get("thumbnail_prompts") or [])]
    for i, tp in enumerate(tps):
        if i < len(new_overlays) and str(new_overlays[i]).strip():
            tp["overlay_text"] = str(new_overlays[i]).strip()
    if tps:
        out["thumbnail_prompts"] = tps
    logger.info(f"translate_metadata: {src_lang}→{target_lang}, {len(out.get('titles', []))} тайтлов")
    return out


def _inject_real_timestamps(description: str, chapters: list[dict],
                            llm_labels) -> str:
    """Вставляет блок TIMESTAMPS с реальными временами перед хэштегами."""
    import re

    # выпиливаем LLM-блок TIMESTAMPS и одинокие строки-тайминги
    description = re.sub(r"(?im)^time?stamps?:?\s*$\n?", "", description)
    description = re.sub(r"(?m)^\d{1,2}:\d{2}(?::\d{2})?\s+.*$\n?", "", description)
    description = re.sub(r"(?m)^\(.*timestamps.*\)$\n?", "", description, flags=re.IGNORECASE)

    # подписи: LLM-метки только для известных времён, фолбэк — hint главы
    label_by_time = {}
    if isinstance(llm_labels, list):
        for item in llm_labels:
            if isinstance(item, dict) and item.get("time"):
                label_by_time[str(item["time"]).strip()] = str(item.get("label", "")).strip()

    lines = ["TIMESTAMPS:"]
    for c in chapters:
        t = str(c["time"]).strip()
        label = label_by_time.get(t) or c.get("hint") or ""
        lines.append(f"{t} {label}".rstrip())
    block = "\n".join(lines)

    # вставка перед финальными хэштегами, иначе в конец
    m = re.search(r"\n(#\w[^\n]*)\s*$", description)
    if m:
        return description[: m.start()].rstrip() + "\n\n" + block + "\n\n" + m.group(1).strip() + "\n"
    return description.rstrip() + "\n\n" + block + "\n"


def build_publish_md(metadata: dict, lang: str = "de") -> str:
    """Markdown для копипаста в YouTube Studio: открыл файл — скопировал нужное.

    Счётчики лимитов YouTube: тайтл ≤100 зн., все теги вместе ≤500 зн.
    """
    import re
    L = []
    titles = metadata.get("titles") or []
    titles_ru = metadata.get("titles_ru") or []
    titles_ab = metadata.get("titles_ab") or []

    L.append("# Публикация на YouTube")
    L.append("")
    L.append("## Title — 3 варианта для A/B-теста")
    L.append("")
    for i, t in enumerate(titles):
        warn = " ⚠️ ДЛИННЕЕ 100 — YouTube обрежет!" if len(t) > 100 else ""
        L.append(f"### Вариант {i+1} ({len(t)} зн.){warn}")
        L.append("")
        L.append("```")
        L.append(t)
        L.append("```")
        if i < len(titles_ru):
            L.append(f"RU: {titles_ru[i]}")
        if i < len(titles_ab) and isinstance(titles_ab[i], dict):
            ab = titles_ab[i]
            L.append(f"CTR-потенциал ~{ab.get('score', '?')}% — {ab.get('why_ru', '')}")
        L.append("")

    L.append("## Description — копировать блок целиком")
    L.append("")
    L.append("```")
    L.append(str(metadata.get("description", "")).strip())
    L.append("```")
    L.append("")

    tags = [str(t) for t in (metadata.get("tags") or [])]
    tags_line = ", ".join(tags)
    warn = " ⚠️ БОЛЬШЕ 500 — YouTube отклонит, убери часть!" if len(tags_line) > 500 else ""
    L.append(f"## Tags — одной строкой ({len(tags_line)}/500 зн.){warn}")
    L.append("")
    L.append("```")
    L.append(tags_line)
    L.append("```")
    L.append("")

    hashtags = re.findall(r"#\w+", str(metadata.get("description", "")))
    if not hashtags:
        hashtags = ["#" + t.replace(" ", "") for t in tags[:5]]
    L.append("## Hashtags")
    L.append("")
    L.append("```")
    L.append(" ".join(hashtags))
    L.append("```")
    L.append("")

    L.append("## Thumbnail-промпты (GPT Image / Midjourney)")
    L.append("")
    for j, tp in enumerate(metadata.get("thumbnail_prompts") or []):
        if not isinstance(tp, dict):
            # LLM иногда отдаёт строки вместо словарей — не падаем
            L.append(f"**Вариант {j+1}.** `{tp}`")
            L.append("")
            continue
        L.append(f"**Вариант {j+1}.** {tp.get('concept','')}")
        L.append(f"- Текст на превью: **{tp.get('overlay_text','')}**")
        L.append(f"- Prompt: `{tp.get('image_prompt','')}`")
        L.append("")

    if metadata.get("pinned_comment"):
        L.append("## Первый комментарий (закрепить сразу после публикации)")
        L.append("")
        L.append("```")
        L.append(str(metadata["pinned_comment"]).strip())
        L.append("```")
        L.append("")

    shorts = metadata.get("shorts_moments") or []
    if shorts:
        L.append("## Shorts — лучшие моменты для нарезки")
        L.append("")
        L.append("> Открой в DaVinci, найди тайминги, вырежи вертикально (9:16), наложи текст оверлея.")
        L.append("")
        for j, s in enumerate(shorts):
            if not isinstance(s, dict):
                continue
            start = s.get("start", "?")
            end = s.get("end", "?")
            dur = s.get("duration_sec", "?")
            L.append(f"### Short {j+1} — {start}–{end} ({dur} сек)")
            L.append(f"**Хук (первые 2 сек):** {s.get('hook', '')}")
            L.append(f"**Текст оверлея:** `{s.get('overlay_text', '')}`")
            L.append(f"**Почему зайдёт:** {s.get('why_ru', '')}")
            L.append(f"**Как резать:** {s.get('cut_note', '')}")
            L.append("")

    if metadata.get("description_ru"):
        L.append("## Описание по-русски (для понимания, НЕ публиковать)")
        L.append("")
        L.append(str(metadata["description_ru"]).strip())
        L.append("")

    return "\n".join(L) + "\n"


# Обратная совместимость: старое имя использовалось orchestrator'ом
build_publish_text = build_publish_md
