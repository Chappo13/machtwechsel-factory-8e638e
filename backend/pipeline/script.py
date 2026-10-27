"""
Script generation and improvement pipeline.

Phase 1: Generate script from topic using LLM
Phase 2: Improve script quality (3 iterations)
  - Iteration 1: Local fix (synonyms, repetitions)
  - Iteration 2: LLM fix (forbidden patterns, weak hooks)
  - Iteration 3: Final polish + fact verification
"""

import asyncio
import logging
import re
from pathlib import Path

from backend.config import get_model_config, get_patterns, get_channel_config
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Секции, после которых модель скатывается в режиссёрские ремарки
# («Musik setzt ein», «Die Kamera schwenkt», «Credits rollen») — диктор
# зачитывал их вслух, а в конце видео появлялись 5 минут чёрных титров.
_DIRECTOR_TAIL_RE = re.compile(
    r"^\s*\*{0,2}\[(ABSPANN|NACHTRAG|FORTSETZUNG|EPILOG|OUTRO|POST.?CREDIT|CREDITS)\b",
    re.IGNORECASE | re.MULTILINE,
)


def strip_director_tail(script: str) -> str:
    """Отрезает хвост сценария начиная с первой пост-продакшн секции."""
    m = _DIRECTOR_TAIL_RE.search(script)
    if not m:
        return script
    logger.warning(
        f"strip_director_tail: отрезан хвост с «{m.group(0).strip()}» "
        f"({len(script) - m.start()} симв)"
    )
    return script[: m.start()].rstrip()


_LANG_NAMES = {"de": "German", "es": "Spanish", "en": "English", "fr": "French"}


async def translate_script(text: str, src_lang: str, target_lang: str, topic: str = "") -> str:
    """Перевести готовый сценарий src_lang→target_lang для мульти-язык фичи
    (те же картинки/музыка, другой голос). Сохраняем структуру, абзацы, смысл,
    числа/факты и curiosity-тон от первого лица; на выходе чистый целевой язык
    без markdown. Длина держится близко к оригиналу — иначе ретайм картинок
    разъедется (немецкий обычно длиннее, это by design растягивает кадры)."""
    src_name = _LANG_NAMES.get(src_lang, src_lang)
    tgt_name = _LANG_NAMES.get(target_lang, target_lang)
    cfg = get_model_config("translation")
    prompt = (
        f"You are a professional video-script translator. Translate the following "
        f"narration script from {src_name} into {tgt_name}.\n\n"
        f"STRICT RULES:\n"
        f"- Keep the EXACT paragraph/line structure — same number of paragraphs, same order.\n"
        f"- Preserve meaning, all numbers, facts, names and dates exactly.\n"
        f"- Keep the warm, calm, first-person curiosity tone (a smart friend sharing a "
        f"discovery). Translate first/second person naturally (e.g. Spanish 'yo/tú' → "
        f"German 'ich/du').\n"
        f"- Natural, fluent, native {tgt_name} — NOT a literal word-for-word calque.\n"
        f"- Keep total length close to the original (do not summarize or expand).\n"
        f"- Output ONLY the translated narration. No notes, no markdown, no headers, "
        f"no quotes around the text, no language labels.\n\n"
        f"SCRIPT TO TRANSLATE:\n{text}"
    )
    out = await call_llm(
        prompt=prompt,
        model=cfg["primary"],
        temperature=cfg.get("temperature", 0.5),
        max_tokens=cfg.get("max_tokens", 32000),
        fallback_model=cfg.get("fallback"),
    )
    out = strip_director_tail((out or "").strip())
    # Гард усадки: перевод не должен схлопнуть сценарий (LLM иногда «суммирует»).
    # <0.8 длины оригинала — почти наверняка обрезка/ошибка → отдаём, но громко.
    if len(out) < 0.8 * len(text):
        logger.warning(
            f"translate_script: перевод {src_lang}→{target_lang} вышел коротким "
            f"({len(text)}→{len(out)} симв) — возможна усадка")
    if not out:
        raise RuntimeError(f"translate_script: пустой перевод {src_lang}→{target_lang}")
    return out


async def generate_script(
    topic: str,
    lang: str,
    duration_minutes: int = 22,
    source_transcripts: list[dict] | None = None,
) -> str:
    """
    Generate a documentary script for a given topic.

    Args:
        topic: Video topic (e.g. "Wirecard Skandal")
        lang: Language code (de, es, en)
        duration_minutes: Target video duration
        source_transcripts: Optional list of {url, title, transcript} dicts from
            fetch_transcripts(). If provided, the LLM uses them as factual context —
            real numbers, events, names — while writing an original script.

    Returns:
        Generated script text
    """
    model_config = get_model_config("script_generation")

    # Load language-specific prompt template
    prompt_path = PROMPTS_DIR / f"script-{lang}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"No prompt template for language: {lang}")

    template = prompt_path.read_text(encoding="utf-8")

    # Calculate target length
    patterns = get_patterns(lang)
    # es выровнен с judge-hints и voices.yaml (было 830 → видео не дотягивало до 8 мин)
    chars_per_min = {"de": 910, "es": 900, "en": 900, "vi": 1000}.get(lang, 850)
    target_chars = duration_minutes * chars_per_min

    # Build source context block from transcripts
    source_context = _build_source_context(source_transcripts, lang)

    prompt = template.format(
        topic=topic,
        duration_minutes=duration_minutes,
        target_characters=target_chars,
        min_characters=int(target_chars * 0.9),
        max_characters=int(target_chars * 1.1),
        source_context=source_context,
    )
    
    min_chars = int(target_chars * 0.98)

    # Основной путь: посекционная генерация (outline → секции по очереди).
    # Монолитный вызов упирается в потолок длины одного ответа (~12-15k симв),
    # а посекционно каждая часть сразу пишется в полный бюджет.
    try:
        script = await _generate_sectioned(
            topic=topic, lang=lang, target_chars=target_chars,
            duration_minutes=duration_minutes, template=prompt,
            model_config=model_config)
    except Exception as e:
        logger.warning(f"Посекционная генерация не удалась ({e}) → монолитный fallback")
        script = strip_director_tail(await call_llm(
            prompt=prompt,
            model=model_config["primary"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
            fallback_model=model_config.get("fallback"),
        ))

    # Страховка на недобор (модели пишут короче запрошенного):
    # посекционное расширение добивает дефицит параллельными вызовами
    if len(script) < min_chars:
        script = await expand_script_sections(
            script, lang, target_chars=target_chars, model_config=model_config)

    # Служебные **[...]**-заголовки секций убираем из финального текста (после expand,
    # которому они ещё нужны для разбивки): иначе TTS читает их вслух, судья штрафует.
    script = _strip_section_headers(script)

    logger.info(f"Generated script: {len(script)} chars (target: {target_chars})")
    return script


def _validate_outline_loops(outline: list) -> list[str]:
    """Проверяет реестр петель outline (opens_loops/pays_off_loops) чистыми
    строковыми операциями, без LLM. Возвращает список нарушений (пусто = ок).
    Если реестра нет ни в одной секции (старый формат) — пропускаем (return [])."""
    def _norm(s) -> str:
        return re.sub(r"\s+", " ", str(s)).strip().lower()

    def _loops(item, key) -> list[str]:
        v = item.get(key, []) if isinstance(item, dict) else []
        if not isinstance(v, list):
            return []
        return [_norm(x) for x in v if str(x).strip()]

    if not outline or not isinstance(outline, list):
        return []
    has_ledger = any(_loops(it, "opens_loops") or _loops(it, "pays_off_loops") for it in outline)
    if not has_ledger:
        return []  # старый формат без реестра — не валидируем

    violations: list[str] = []
    n = len(outline)

    # карта: петля -> минимальный индекс секции, где она ЗАКРЫТА / ОТКРЫТА
    payoff_idx: dict[str, int] = {}
    opened_at: dict[str, int] = {}
    for j, it in enumerate(outline):
        for loop in _loops(it, "pays_off_loops"):
            payoff_idx.setdefault(loop, j)
        for loop in _loops(it, "opens_loops"):
            opened_at.setdefault(loop, j)

    # (a) каждая петля из хука (секция 0) закрывается позже
    hook_loops = _loops(outline[0], "opens_loops")
    for loop in hook_loops:
        if loop not in payoff_idx:
            violations.append(f'hook loop never paid off: "{loop[:60]}"')

    # climax = секция с максимальной strength
    def _strength(it) -> float:
        try:
            return float(it.get("strength", 0) or 0)
        except (TypeError, ValueError):
            return 0.0
    climax_idx = max(range(n), key=lambda j: _strength(outline[j])) if n else 0

    # (b) >= 2 петель хука закрыты ПОСЛЕ кульминации
    paid_after_climax = sum(
        1 for loop in hook_loops if payoff_idx.get(loop, -1) > climax_idx
    )
    if hook_loops and paid_after_climax < 2:
        violations.append(f"only {paid_after_climax} hook-loops paid off after climax (need >=2)")

    # (c) петля закрывается не раньше чем через 2 секции после открытия
    for loop, j in payoff_idx.items():
        i = opened_at.get(loop)
        if i is not None and (j - i) < 2:
            violations.append(f'loop resolved too fast ({j - i} sections): "{loop[:50]}"')

    # (d) макро-петля: если задана ровно одна — в последних 2-3 секциях
    macro = [j for j, it in enumerate(outline) if isinstance(it, dict) and it.get("closes_macro_loop")]
    if len(macro) == 1 and macro[0] < n - 3:
        violations.append(f"closes_macro_loop at section {macro[0]} — must be in last 3")

    return violations


async def _generate_sectioned(
    topic: str,
    lang: str,
    target_chars: int,
    duration_minutes: int,
    template: str,
    model_config: dict,
) -> str:
    """Outline → секции по очереди → склейка.

    Каждый секционный вызов видит правила стиля (template), бриф своей секции,
    хвост предыдущей (стык) и резюме уже написанного (анти-повтор).
    """
    lang_names = {"de": "German", "es": "Spanish", "en": "English", "vi": "Vietnamese"}
    lang_name = lang_names.get(lang, lang)

    # Размер/число секций масштабируются от target_chars. Раньше было захардкожено
    # «9-13 секций по 1300-1800» (под 20-мин Rise&Fall) → для 8-мин видео давало ~17 мин.
    cpm = max(1, round(target_chars / max(1, duration_minutes)))
    hook_chars = 900 if target_chars >= 6000 else max(450, int(target_chars * 0.11))
    closing_chars = 600 if target_chars >= 6000 else max(350, int(target_chars * 0.08))
    story_budget = max(target_chars - hook_chars - closing_chars, 1400)
    n_story = max(3, round(story_budget / 1500))
    sec_chars = max(900, round(story_budget / n_story))

    # Формат-aware: curiosity-каналы (es/vi «Otra Mirada»/«Ngẫm») — тёплое эссе-загадка,
    # НЕ Rise&Fall триллер. Раньше каркас был жёстко story (collapse/climax/протагонист) и
    # уводил curiosity в дистопический триллер с выдуманными исследованиями.
    is_curiosity = False
    try:
        is_curiosity = str((get_channel_config(lang) or {}).get("niche", "")).startswith("curiosity")
    except Exception:
        is_curiosity = lang in ("es", "vi")
    n_evidence = max(3, n_story - 2)
    beat_enum = ("curiosity|surprise|wonder|revelation|warmth|reflection"
                 if is_curiosity else "shock|tension|revelation|relief|dread")

    if is_curiosity:
        structure_block = f"""Structure requirements — WARM CURIOSITY ESSAY (this channel is a calm, warm, first-person essayist exploring a strange question about history, psychology or the human body; it is NOT a thriller, NOT crime, NOT dystopia, NOT a courtroom drama — there is NO villain, NO collapse, NO protagonist who loses everything):
- First: a HOOK / MIRROR section (~{hook_chars} chars, ~45s) — open by describing what the listener is doing RIGHT NOW (a small, ordinary present-moment scene: scrolling a phone, lying awake, eating), then twist it into the strange question of the video. Warm, personal, first person. End on a curiosity gap BEFORE giving any history. emotional_beat: curiosity. List the central question in opens_loops.
- Second: INVERT THE ASSUMPTION (~{sec_chars} chars) — gently debunk the obvious assumption the listener holds, so they feel they are about to learn something they had wrong. emotional_beat: surprise.
- Then {n_evidence} EVIDENCE sections (~{sec_chars} chars each) — each delivers ONE concrete, fascinating fact: a REAL verifiable detail, a vivid little scene, and what it reveals about us. FRONT-LOADING (critical): put the TWO most surprising facts in the FIRST evidence sections, right after the hook — NEVER save the best for last. emotional_beat: wonder/revelation.
- Then: ESCALATE TO THE BIG IDEA (~{sec_chars} chars) — connect the evidence ALREADY shown into one counter-intuitive, slightly philosophical thesis. emotional_beat: revelation.
- Last: LOOP BACK TO NOW + warm close (~{closing_chars} chars) — snap back to the present-moment scene from the hook, close that loop, land on ONE warm, human, philosophical thought. NO "like & subscribe"/CTA. emotional_beat: warmth.
- The sum of "chars" must be ≈ {target_chars}
- TRUTH OVER DRAMA (most important): use REAL, verifiable facts — the kind found in books or Wikipedia. If you do NOT know a real named study, use an honest general framing ("researchers have found", "we know that…") — NEVER invent a researcher, institution, year or percentage, and NEVER describe a study as "unpublished/archived/secret/suppressed" (that is a fabrication tell that destroys the channel's trust).
- NO DYSTOPIA / NO THRILLER: never turn the topic into AI surveillance, hidden sensors, corporations tracking people, lawsuits, or a crime story. Keep it about the human being and history — warm and wondering.
- CURIOSITY GAP per section: each section opens or advances ONE genuine question and ends teasing the next ("and that is the strangest part…"). Woven naturally, NEVER "remember this number".
- emotional_beat must stay within: {beat_enum} — NEVER shock, dread or tension.
- BACKGROUND IS SHORT: weave any context into the wonder; no dry history block.
- CURIOSITY-DRIVEN HEADERS: tease, never label.
- NO credits/epilogue sections.
- Headers in {lang_name}, timestamps approximate"""
    else:
        structure_block = f"""Structure requirements:
- First: a COLD-OPEN HOOK section (~{hook_chars} chars, ~60s) built as a 5-beat structure: (1) a provocative verdict OR a jump into the hardest concrete scene — no warm-up, never a question; (2) ONE number showing the scale of the later collapse PLUS one line naming WHO it hit and what was at stake (money, savings, pension, jobs, trust — identity-threat THROUGH the people affected, never the empty "imagine if"); (3) one subversion line breaking the expectation; (4) an OPEN-LOOP STACK of 2-4 named, UNRESOLVED cliffhangers (list them in this item's opens_loops); (5) one payoff-preview — VARY it across videos between (a) a central open question (the macro-loop), (b) a knowledge/exclusivity promise, or (c) one last hard fact; avoid the formulaic "How could X … and who Y?". Name the ONE protagonist/conflict the viewer follows to the end.
- Then {n_story} STORY sections (~{sec_chars} chars each) forming ONE narrative arc: setup & stakes → rise → first cracks → build-up → the CLIMAX → fallout → human consequences → present day.
- Last: a short reflective closing (~{closing_chars} chars) — a resonant final thought, NO "like & subscribe" / CTA boilerplate.
- The sum of "chars" must be ≈ {target_chars}
- ONE CLIMAX: mark exactly ONE section as the dramatic peak (give it the highest "strength"); build toward it and fall away from it. Do NOT make several equally-loud sections — that flattens the arc.
- FRONT-LOADING (critical for retention): the cold open PLUS the next 2-3 sections must contain the 2-3 most shocking reveals of the whole story — do NOT hold them back. The FIRST HALF must have clearly higher average "strength" than the second.
- BACKGROUND IS SHORT: at most ONE setup/context section, and even it must carry tension — never a long dry history block. Weave context into the action. No two consecutive sections may both be pure exposition.
- OPEN-LOOP LEDGER (this is what keeps the 2nd half alive — enforced after you return): use opens_loops / pays_off_loops on every item. HARD REQUIREMENTS: (a) every loop in the cold-open's opens_loops MUST appear in some later section's pays_off_loops; (b) at least 2 of the hook-stack loops are paid off AFTER the climax section (not before); (c) a loop is paid off only after at least 2 sections have passed (no instant resolution); (d) open the next loop before closing the previous one, so a payoff and a fresh tease overlap. Loop strings in pays_off_loops MUST be copied VERBATIM (same wording) from the earlier opens_loops entry.
- LOOP CADENCE PER MINUTE: narration runs ~{cpm} chars/min, so EVERY section opens or advances at least one loop, and any section over ~1500 chars carries TWO (one mid, one at the end). Never plan a stretch >3 min (~2700 chars of consecutive sections) without a loop opening or closing. Driven by the STORY, never "remember this number".
- SECOND HALF IS NOT CLEANUP: tag every post-climax section reopen=true — it must OPEN with a re-hook (new question, unexpected turn, or still-unresolved consequence), not a summary. Plan at least ONE fresh twist/stakes-escalation after the climax (a second betrayal, an unforeseen consequence, a person whose fate is still open). The back half carries the SAME loop-density as the first half.
- MACRO LOOP: when the cold-open's beat-5 is a central question, exactly ONE late section (within the last 2-3) sets closes_macro_loop=true and answers it — never mid-video.
- EVERY CONTENT SECTION CARRIES TENSION: set "carries"; a "2013-losses" or "2010-scheme" section must be a person, a decision, or a consequence, not a data list.
- NUMBER DISCIPLINE: spread facts across the arc; NO section is a dense statistics dump. Each section advances the STORY, not a list of figures.
- CURIOSITY-DRIVEN HEADERS: section names TEASE, never label — e.g. "The call that started it all", "The gap in the books" — NOT "Background", "Development", "Conclusion".
- Vary "emotional_beat" so the curve rises and falls (not flat).
- NO ABSPANN/EPILOG/NACHTRAG/credits sections.
- Headers in {lang_name}, timestamps approximate"""

    outline_prompt = f"""Plan the section structure for a {lang_name} {'warm curiosity-essay' if is_curiosity else 'documentary'} script about: {topic}
Total length: {target_chars} characters (~{duration_minutes} minutes of narration, ~{cpm} chars/min).

Return ONLY a JSON array, each item:
{{"header": "**[<NAME>: <M:SS-M:SS>]**", "brief": "<1-2 sentences: the beat this section delivers — a scene, an idea, a reveal; NEVER a list of figures/dates>",
  "chars": <int>, "emotional_beat": "<{beat_enum}>",
  "carries": "<reveal|turn|human-stakes|escalation|payoff — what THIS section delivers; never pure exposition>",
  "cliffhanger": "<one teasing sentence that makes the viewer NEED the next section>",
  "opens_loops": ["<each genuine, NOT-resolved question/curiosity this section TEASES>"],
  "pays_off_loops": ["<earlier loop string this section finally ANSWERS — copied VERBATIM from the earlier opens_loops entry>"],
  "reopen": <true for later sections — this section must OPEN with a re-hook, not a summary>,
  "closes_macro_loop": <true on the ONE late section that answers the hook's central question>,
  "strength": <1-10: how gripping this section's material is>}}

{structure_block}"""

    outline_raw = await call_llm(
        prompt=outline_prompt,
        model=model_config["primary"],
        temperature=model_config["temperature"],
        max_tokens=4000,
        fallback_model=model_config.get("fallback"),
    )
    outline_raw = outline_raw.strip()
    if outline_raw.startswith("```"):
        outline_raw = outline_raw.split("\n", 1)[1].rsplit("```", 1)[0]
    import json as _json
    outline = _json.loads(outline_raw)
    if not (isinstance(outline, list) and len(outline) >= 5):
        raise ValueError(f"outline слишком короткий: {len(outline) if isinstance(outline, list) else outline}")

    # Реестр петель: хук-петли должны закрываться позже и распределяться после
    # кульминации (удержание 2-й половины). При нарушениях — ОДНА регенерация,
    # затем продолжаем в любом случае (никогда не блокируем прогон).
    # curiosity-эссе не имеет climax/post-climax payoff — story-валидатор петель там
    # даёт ложные нарушения и зря перегенерит. Для curiosity пропускаем.
    violations = [] if is_curiosity else _validate_outline_loops(outline)
    if violations:
        logger.warning("outline: нарушения реестра петель (%s) — регенерирую один раз",
                       "; ".join(violations[:6]))
        fix_prompt = (
            outline_prompt
            + "\n\nThe previous outline VIOLATED these open-loop-ledger rules. "
            + "Fix them and return the CORRECTED full JSON array (keep verbatim loop strings):\n- "
            + "\n- ".join(violations)
        )
        try:
            fixed_raw = (await call_llm(
                prompt=fix_prompt,
                model=model_config["primary"],
                temperature=model_config["temperature"],
                max_tokens=4000,
                fallback_model=model_config.get("fallback"),
            )).strip()
            if fixed_raw.startswith("```"):
                fixed_raw = fixed_raw.split("\n", 1)[1].rsplit("```", 1)[0]
            fixed = _json.loads(fixed_raw)
            if isinstance(fixed, list) and len(fixed) >= 5:
                v2 = _validate_outline_loops(fixed)
                if len(v2) <= len(violations):
                    outline = fixed
                    logger.info("outline: реестр после регенерации — %d нарушений (было %d)",
                                len(v2), len(violations))
        except Exception as e:
            logger.warning("outline: регенерация не удалась (%s) — оставляю исходник", e)

    sections: list[str] = []
    summaries: list[str] = []
    n_sections = len(outline)

    # Правила содержания секции зависят от формата: story (числа/протагонист/коллапс)
    # vs curiosity (один факт + тёплая сцена, анти-фабрикация, анти-дистопия).
    if is_curiosity:
        content_rules = (
            "- ONE FASCINATING FACT, NOT A DATA DUMP: deliver ONE concrete, surprising fact and what it reveals about us — never a list of figures. At most one or two numbers, and only if they are REAL.\n"
            "- MAKE IT HUMAN AND CONCRETE: a tiny vivid scene, a sensory image, a feeling the listener can picture — curiosity and warmth, never a roll-call of dates.\n"
            "- TONE GUARD: stay warm, calm and wondering. NEVER drift into AI surveillance, hidden sensors, corporations, lawsuits, crime or dystopia — there is no villain here."
        )
        antifab_line = (
            "- TRUTH OVER DRAMA: use only REAL, verifiable facts. If you do not know a real named study, write \"researchers have found\" / \"we know that\" — NEVER invent a researcher, institution, year or percentage, and NEVER describe a study as unpublished/archived/secret/suppressed."
        )
    else:
        content_rules = (
            "- HARD NUMBER LIMIT (anti-flat): at most 2-3 truly important numbers in this section; NEVER two data-heavy sentences back to back; a number arrives as the ANSWER to a posed question, never as a list.\n"
            "- NUMBER = PERSON + COMPARISON + CONSEQUENCE: every important number gets a human anchor (who it happened to), a graspable comparison, and a consequence — or it is cut. A bare number is logic; number + person + consequence is emotion.\n"
            "- STORY, NOT ROLL-CALL: advance the STORY — one scene, one decision, one consequence — not a list of losses or dates. Return to the ONE protagonist where the story allows."
        )
        antifab_line = (
            "- Do NOT invent sources: if a number is uncertain, phrase it as an estimate IN THE SCRIPT'S OWN LANGUAGE rather than attributing a fake study/institution."
        )
    for k, item in enumerate(outline):
        header = str(item.get("header", f"**[TEIL {k}]**")).strip()
        brief = str(item.get("brief", ""))
        chars = int(item.get("chars", 1500) or 1500)
        cliffhanger = str(item.get("cliffhanger", "")).strip()
        beat = str(item.get("emotional_beat", "")).strip()
        carries = str(item.get("carries", "")).strip()
        reopen = bool(item.get("reopen"))

        def _loop_list(key: str) -> str:
            v = item.get(key, [])
            if not isinstance(v, list):
                return ""
            return " | ".join(str(x).strip() for x in v if str(x).strip())
        opens_loops = _loop_list("opens_loops")
        pays_off_loops = _loop_list("pays_off_loops")
        is_last = (k == n_sections - 1)

        prev_tail = sections[-1][-1200:] if sections else "(this is the first section)"
        summary_block = "\n".join(summaries) if summaries else "(nothing yet)"

        # cliffhanger-инструкция: каждая секция (кроме финала) обязана закончиться
        # крючком к следующей; финал — рефлексия + тизер сиквела (как в шаблоне)
        cliff_line = (
            "End with the closing/CTA as in the style rules (reflective question + sequel teaser)."
            if is_last else
            f'END THIS SECTION WITH A CLIFFHANGER/OPEN QUESTION that makes the next section feel necessary'
            + (f' (planned hook: "{cliffhanger}")' if cliffhanger else '')
            + '. Do NOT resolve it here.'
        )
        # Реестр петель этой секции → точные инструкции что заложить/закрыть
        open_line = (
            'OPEN with a RE-HOOK (a new question, an unexpected turn, or a still-unresolved '
            'consequence), phrased FRESH out of this section — NEVER a summary or "wie wir '
            'gesehen haben", and never a reused opener. This is a 2nd-half section.'
            if reopen else
            'OPEN by advancing or closing an earlier open loop, or opening a fresh one out of the '
            'story — never flat exposition, never filler ("Aber das ist noch nicht alles").'
        )
        loop_line = (
            (f'PLANT these open loops here (verbatim, woven into the story, do NOT resolve them): {opens_loops}. '
             if opens_loops else 'Plant at least ONE open loop here, woven into the story. ')
            + (f'PAY OFF here — and only here — these earlier loops (use the SAME wording the viewer heard): {pays_off_loops}.'
               if pays_off_loops else '')
        )

        section_prompt = f"""{template}

---
You are writing the script SECTION BY SECTION. Sections already written (summaries — do NOT repeat these facts or phrasings):
{summary_block}

End of the previous section (connect smoothly to it):
...{prev_tail}

Now write ONLY this section:
{header}
Plan: {brief}
Emotional beat: {beat or "keep it gripping"}. This section carries: {carries or "tension"}.
Length: ~{chars} characters of pure narration.

Section rules:
- MINI RE-HOOK AT THE START: {open_line}
- OPEN LOOPS: {loop_line} If this section is over ~1500 chars, plant TWO loops (one mid, one at the end). Woven into the story, NEVER mechanical ("merken Sie sich diese Zahl"). Open the NEXT loop before the previous one closes — a payoff and a fresh tease overlap. CRITICAL: phrase EVERY loop in a FRESH sentence built from THIS section's own content — NEVER reuse a loop sentence wording from another section, and never a template phrasing; if a loop sentence would echo one already used, rewrite it differently.
{content_rules}
- PATTERN INTERRUPT (carried in the text for TTS): change something audible at least every ~90-120s — a hard pace shift (a 3-7 word punchy sentence right after a long one), a perspective switch, or a deliberate pause. No more than 3 long sentences in a row; no sentence over ~25 words.
- {cliff_line}
{antifab_line}

Start with the header line exactly as given, then the narration text. No other output, no stage directions, no meta-comments."""

        body = await call_llm(
            prompt=section_prompt,
            model=model_config["primary"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
            fallback_model=model_config.get("fallback"),
        )
        body = strip_director_tail(body.strip())
        if not body:
            logger.warning(f"Секция {k+1} '{header}' пустая — пропускаю")
            continue
        if not body.startswith("**["):
            body = header + "\n" + body
        if k == 0:
            if is_curiosity:
                # curiosity-хук: финанс best-of-N (verdict/mid-scene jump) — это
                # ПРОТИВОПОЛОЖНОСТЬ зеркалу. Вместо него — enforcement зеркала зрителя.
                body = await _enforce_curiosity_mirror(
                    body, header, brief, topic, lang, model_config)
            else:
                ctx = " ".join(
                    str(o.get("brief", "")) for o in outline[1:4] if isinstance(o, dict)
                )
                story_brief = (brief + " " + ctx).strip()
                body = await _maybe_best_hook(
                    body, header, story_brief, opens_loops, topic, lang, template)
        sections.append(body)
        # резюме для анти-повтора: заголовок + первые 160 симв текста
        text_only = body.split("\n", 1)[1] if "\n" in body else body
        summaries.append(f"- {header}: {text_only[:160]}")
        logger.info(f"Секция {k+1}/{len(outline)}: {len(body)} симв (план {chars})")

    if len(sections) < 4:
        raise ValueError(f"только {len(sections)} секций сгенерировано")
    return "\n\n".join(sections)


_SECTION_HEADER_RE = re.compile(r"^\s*\*\*\[[^\]]+\]\*\*\s*$", re.MULTILINE)


def _split_sections(script: str) -> list[tuple[str, str]]:
    """Разбивает сценарий на (заголовок, тело) по **[...]**-заголовкам.

    Текст до первого заголовка идёт секцией с пустым заголовком.
    """
    sections = []
    headers = list(_SECTION_HEADER_RE.finditer(script))
    if not headers:
        return [("", script)]
    if headers[0].start() > 0:
        preamble = script[: headers[0].start()].strip()
        if preamble:
            sections.append(("", preamble))
    for k, m in enumerate(headers):
        body_end = headers[k + 1].start() if k + 1 < len(headers) else len(script)
        sections.append((m.group(0).strip(), script[m.end(): body_end].strip()))
    return sections


async def expand_script_sections(
    script: str,
    lang: str,
    target_chars: int,
    model_config: dict,
    max_rounds: int = 2,
) -> str:
    """Добивает сценарий до target_chars посекционным расширением.

    Модель не выдаёт 20k+ символов одним ответом (обрыв на ~12-15k, дальше
    continuation скатывался в ремарки) — а «дополни ЭТУ секцию деталями на
    +N%» в комфортной длине, и секции расширяются параллельно.
    """
    lang_names = {"de": "German", "es": "Spanish", "en": "English", "vi": "Vietnamese"}
    lang_name = lang_names.get(lang, lang)

    for round_no in range(max_rounds):
        if len(script) >= target_chars * 0.95:
            break
        sections = _split_sections(script)
        # HOOK и PRE-PAYOFF не трогаем — первые секунды должны остаться плотными
        candidates = [
            k for k, (h, body) in enumerate(sections)
            if k >= 2 and len(body) >= 200
        ]
        if not candidates:
            break
        deficit = target_chars - len(script)
        add_per = deficit // len(candidates)
        if add_per < 250:
            break  # дотягивать по 100 символов на секцию — шум, не контент

        async def _expand_one(k: int) -> tuple[int, str]:
            header, body = sections[k]
            add = min(add_per, int(len(body) * 0.8))
            prompt = (
                f"You are expanding ONE section of a {lang_name} narration script "
                f"(factual, retention-driven; keep its existing tone — warm curiosity or documentary).\n"
                f"Expand it from {len(body)} to about {len(body) + add} characters.\n\n"
                f"ADD: vivid scenes and human detail around facts ALREADY in the section "
                f"— what a person saw, did, decided; sensory and emotional concreteness; "
                f"concrete consequences; smooth in-section transitions. Add STORY, not exposition.\n"
                f"DO NOT: invent new numbers, dates or names (only facts already in the "
                f"section); add rhetorical questions to the viewer; turn the section into "
                f"explanation or a list of figures; change the FIRST or LAST sentence (they "
                f"connect to neighboring sections); add section headers, markdown, stage "
                f"directions (camera/music/cut) or meta-comments.\n"
                f"Write in {lang_name}. Return ONLY the expanded section text.\n\n"
                f"SECTION:\n{body}"
            )
            try:
                out = await call_llm(
                    prompt=prompt,
                    model=model_config["primary"],
                    temperature=model_config["temperature"],
                    max_tokens=model_config["max_tokens"],
                    fallback_model=model_config.get("fallback"),
                )
            except Exception as e:
                logger.warning(f"expand: секция {k} не расширена ({e}) — оставляю исходник")
                return k, body
            out = strip_director_tail(out.strip())
            # guard: расширение не должно укоротить, вернуть заголовки или markdown
            if len(out) <= len(body) or "**[" in out:
                return k, body
            return k, out

        results = await asyncio.gather(*(_expand_one(k) for k in candidates))
        for k, new_body in results:
            sections[k] = (sections[k][0], new_body)

        script = "\n\n".join(
            f"{h}\n{b}" if h else b for h, b in sections
        )
        logger.info(
            f"expand round {round_no + 1}: {len(script)} chars "
            f"(target {target_chars}, {len(candidates)} секций расширялось)"
        )

    return script


# ── Анти-AI banlist + humanization ───────────────────────────────────────────
# Фразы-маркеры «написано ИИ» / клише. Запрещаем в генерации, вычищаем в
# humanization-проходе и в targeted-improve. Именно их штрафует судья (естественность).
AI_TELL_BANLIST = {
    "de": [
        "Stell dir vor", "Stellen Sie sich vor", "Stellen wir uns vor",
        "Was wäre, wenn", "Was wäre wenn", "Ein System, das", "Ein System das",
        "Das ist die Geschichte von", "Es ist wichtig zu beachten", "Zusammenfassend",
        "Wie wir gesehen haben", "Lass uns eintauchen", "Tauchen wir ein", "Schnall dich an",
        "Das wirst du nicht glauben", "Merken Sie sich diese Zahl", "Merke dir diese Zahl",
        "Aber das ist noch nicht alles", "Doch damit nicht genug", "Überprüfen Sie",
        "Hey Leute", "Willkommen zurück", "In diesem Video", "Schauen wir uns an",
        "Am Ende des Tages", "Eines ist klar", "Ob Sie es glauben oder nicht",
        "Die Wahrheit ist", "Hier ist der Clou", "Einige Experten sagen",
    ],
    "es": [
        "Imagina", "Imagínate", "Qué pasaría si", "Un sistema que",
        "Esta es la historia de", "Es importante señalar", "En resumen",
        "Como hemos visto", "Vamos a sumergirnos", "No vas a creer",
        "Recuerda este número", "Pero eso no es todo", "Al final del día",
        "Una cosa está clara", "La verdad es que", "Bienvenidos de nuevo",
        "En este video", "Algunos expertos dicen", "Y aquí viene lo bueno",
    ],
    "en": [
        "Imagine", "Picture this", "What if", "A system that",
        "This is the story of", "It's important to note", "In conclusion",
        "As we've seen", "Let's dive in", "You won't believe",
        "Remember this number", "But that's not all", "At the end of the day",
        "One thing is clear", "The truth is", "Welcome back",
        "In this video", "Some experts say", "Here's the kicker", "Buckle up",
    ],
    "vi": [
        "Hãy tưởng tượng", "Thử hình dung", "Điều gì sẽ xảy ra nếu", "Một hệ thống",
        "Đây là câu chuyện về", "Điều quan trọng cần lưu ý", "Tóm lại",
        "Như chúng ta đã thấy", "Hãy cùng đi sâu vào", "Bạn sẽ không tin được",
        "Hãy nhớ con số này", "Nhưng đó chưa phải tất cả", "Nói cho cùng",
        "Có một điều chắc chắn", "Sự thật là", "Chào mừng quay trở lại",
        "Trong video này", "Một số chuyên gia nói", "Và đây là điều thú vị",
    ],
}


def _banlist_block(lang: str) -> str:
    return "; ".join(AI_TELL_BANLIST.get(lang, AI_TELL_BANLIST["en"]))


def _strip_section_headers(script: str) -> str:
    """Убирает служебные **[...]**-заголовки секций из финального текста — они нужны
    только для посекционной сборки/анти-повтора, в озвучку и судье попадать НЕ должны
    (TTS читает их вслух, судья штрафует за «markdown/мусор»)."""
    cleaned = _SECTION_HEADER_RE.sub("", script)
    # bare/inline таймкод-заголовки без ** («[El experimento: 5:30-7:40]» где угодно
    # в строке) — _SECTION_HEADER_RE их не ловит (требует ** на всю строку).
    cleaned = re.sub(r"\*{0,2}\[[^\]\n]*\d{1,2}:\d{2}[^\]\n]*\]\*{0,2}", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)  # схлопнуть образовавшиеся пустоты
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


async def humanize_script(script: str, lang: str) -> str:
    """Финальный проход «очеловечивания»: вычищает AI-штампы, выравнивает ритм
    предложений под TTS, убирает навязчивые повторы и клишированные концовки —
    БЕЗ потери фактов/чисел/источников и длины. Возвращает только текст."""
    cfg = get_model_config("script_humanize")
    prompt = f"""You are an expert script doctor for {lang}-language documentary narration.
Rewrite the script below so it reads like a HUMAN wrote it, not an AI. Change ONLY
wording / rhythm / word-choice — keep ALL facts, numbers, sources, names and the story
order EXACTLY. Length within ±5%. The script is in {lang}; keep it in {lang}.
Do NOT touch the first ~900 characters (the cold-open hook) — keep them verbatim.

Do this:
1. Remove or replace these AI-cliché phrases and any similar ones, wherever they appear: {_banlist_block(lang)}.
2. Vary sentence rhythm — break sentences longer than ~25 words; mix short punchy sentences with longer ones. No three same-length sentences in a row. But PRESERVE deliberately SHORT punchy sentences (3-7 words, in the script's own language) used as pace-breaks — do NOT merge them into longer ones.
3. KEEP the story-driven open loops and cliffhangers that link sections (a question or teaser planted in one part and paid off later) — these drive retention, do NOT delete them; just phrase them naturally. Only cut EMPTY rhetorical questions that go nowhere ("Who pays?", "What does that mean?"). Aim for an open loop / hook roughly every 2-3 minutes.
4. Any word repeated unnaturally often → vary it or cut it. CRITICAL: if a whole SENTENCE or distinctive PHRASE recurs (e.g. the same open-loop line used more than once), rewrite each occurrence into a different, fresh sentence — identical recurring sentences are the worst AI tell.
5. Replace any clichéd ending (CTA, "check the...", pathos appeal) with a resonant, concrete closing thought.
6. Concrete images over abstractions; understatement over melodrama; natural spoken phrasing.

Return ONLY the rewritten narration text — no comments, no markdown, no headers.

Script:
{script}"""
    out = await call_llm(
        prompt=prompt, model=cfg["primary"],
        temperature=cfg.get("temperature", 0.6),
        max_tokens=cfg.get("max_tokens", 32000),
        fallback_model=cfg.get("fallback"),
    )
    return strip_director_tail((out or "").strip())


# ── Best-of-N для cold-open хука ──────────────────────────────────────────────
# Пустые формы-открывашки, дисквалифицирующие вариант. Матчим ТОЛЬКО по началу
# ПЕРВОГО предложения (anchored), не подстрокой по всему хуку — иначе убьём
# одобренный сценический заход «Stell dir vor, du legst dein Erspartes…».
HOOK_OPENER_BANLIST = {
    "de": ["Stell dir vor, du könntest", "Was wäre, wenn", "Schnall dich an",
           "Das wirst du nicht glauben", "Hey Leute", "Willkommen", "In diesem Video"],
    "es": ["Imagina que podrías", "Qué pasaría si", "Hola a todos",
           "Bienvenidos", "En este video", "No vas a creer"],
    "en": ["Imagine you could", "What if", "Buckle up",
           "You won't believe", "Hey guys", "Welcome", "In this video"],
    "vi": ["Hãy tưởng tượng", "Điều gì sẽ xảy ra nếu", "Xin chào các bạn",
           "Chào mừng", "Trong video này", "Bạn sẽ không tin được"],
}


def _hook_opener_banned(hook: str, lang: str) -> bool:
    """True, если ПЕРВОЕ предложение хука начинается с пустой формы-открывашки."""
    first = re.split(r"(?<=[.!?])\s", hook.strip(), maxsplit=1)[0]
    first = first.lstrip("„\"'»«— -").lower()
    return any(first.startswith(p.lower()) for p in HOOK_OPENER_BANLIST.get(lang, HOOK_OPENER_BANLIST["en"]))


async def _generate_hook_variants(
    topic: str, lang: str, template: str, story_brief: str,
    planned_loops: str, n: int, cfg: dict,
) -> list[str]:
    """Генерит N вариантов cold-open хука одним вызовом (для разброса)."""
    import json as _json
    lang_name = {"de": "German", "es": "Spanish", "en": "English"}.get(lang, lang)
    prompt = f"""{template}

---
Write {n} DISTINCT cold-open HOOK variants (first ~60 seconds, ~900 characters each,
6-9 sentences) for a {lang_name} documentary about: {topic}

Story brief (use these facts, protagonist and stakes):
{story_brief}

Each variant MUST stack these exact open loops (tease them, do NOT resolve):
{planned_loops or "(derive 2-4 named, unresolved cliffhangers from the story brief)"}

Rules for the SET of {n} variants:
- Follow the 5-beat HOOK structure from the style rules above.
- Vary beat 1: at least 2 open with a provocative verdict, at least 2 jump straight into the hardest concrete scene.
- Each closes on a DIFFERENT beat-5 type (open question / knowledge-promise / hard fact); avoid the formulaic "How could X … and who Y?" template.
- Native, calm, composed — never loud or hawkish, never a greeting / "in this video". Write 100% in {lang}, no foreign words.

Return ONLY a JSON array of {n} strings (the hook texts), nothing else."""
    raw = (await call_llm(
        prompt=prompt, model=cfg["primary"],
        temperature=cfg.get("temperature", 0.9),
        max_tokens=cfg.get("max_tokens", 6000),
        fallback_model=cfg.get("fallback"),
    )).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    arr = _json.loads(raw)
    return [strip_director_tail(str(x).strip()) for x in arr if str(x).strip()]


async def _pick_best_hook(hooks: list[str], lang: str) -> str | None:
    """Микро-судья: дисквалифицирует пустые открывашки, оценивает 5 измерений и
    возвращает лучший хук. None — если судить нечего."""
    import json as _json
    survivors = [h for h in hooks if not _hook_opener_banned(h, lang)] or hooks
    if not survivors:
        return None
    if len(survivors) == 1:
        return survivors[0]
    cfg = get_model_config("script_judge")
    listing = "\n\n".join(f"[{i}] {h}" for i, h in enumerate(survivors))
    prompt = f"""You are a retention editor judging {lang} documentary cold-open hooks.
Score each hook 0-5 on five dimensions, then pick the best:
- first_line: beat 1 is a verdict or mid-scene jump in the FIRST sentence; zero warm-up/greeting; NOT a question.
- identity_threat: concrete stakes tied to WHO it hit (money/jobs/savings/pension/trust), via the affected — no empty "imagine if", no finger-wagging.
- open_loop_stack: 2-4 named, distinct, UNRESOLVED cliffhangers.
- curiosity_gap: a specific central gap (concrete number/date) implicitly promised to be answered.
- natural: native, calm/composed, no AI clichés, TTS-clean, NOT the formulaic "How could X … and who Y?".

HOOKS:
{listing}

Return ONLY JSON: {{"best_index": <int>, "why": "<one line>"}}. Pick by highest total;
tie-break by identity_threat, then curiosity_gap."""
    raw = (await call_llm(
        prompt=prompt, model=cfg["primary"], temperature=0.0,
        max_tokens=cfg.get("max_tokens", 8000), fallback_model=cfg.get("fallback"),
    )).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    verdict = _json.loads(raw)
    idx = int(verdict.get("best_index", 0))
    if not (0 <= idx < len(survivors)):
        idx = 0
    logger.info("hook best-of-%d: выбран #%d — %s",
                len(survivors), idx, str(verdict.get("why", ""))[:80])
    return survivors[idx]


async def _maybe_best_hook(
    body: str, header: str, story_brief: str, planned_loops: str,
    topic: str, lang: str, template: str,
) -> str:
    """Best-of-N для cold-open: N вариантов + секционный хук → микро-судья → лучший.
    Любой сбой (нет конфига, LLM, JSON) → молча возвращаем секционный хук."""
    try:
        cfg = get_model_config("script_hook_variants")
    except Exception:
        return body
    n = int(cfg.get("n", 0) or 0)
    if n <= 1:
        return body
    try:
        variants = await _generate_hook_variants(topic, lang, template, story_brief, planned_loops, n, cfg)
        section_hook = body.split("\n", 1)[1].strip() if "\n" in body else body.strip()
        cands = ([section_hook] if section_hook else []) + variants
        if len(cands) < 2:
            return body
        best = await _pick_best_hook(cands, lang)
        return (header + "\n" + best) if best else body
    except Exception as e:
        logger.warning("hook best-of-N не удался (%s) — оставляю секционный хук", e)
        return body


# ════════════════════════════════════════════════════════════════════════════
# Curiosity: enforcement «хук-зеркала» (только is_curiosity, es «Otra Mirada» /
# vi «Ngẫm»). Curiosity-хук ОБЯЗАН открываться ЗЕРКАЛОМ зрителя: первые 1-2
# предложения = 2-е лицо + СОБСТВЕННЫЙ настоящий момент зрителя (что он делает/
# чувствует ПРЯМО СЕЙЧАС), НЕ далёкая историческая сцена / 3-е лицо / место-эпоха /
# «представь, что…». Best-effort: любой сбой (LLM/JSON) → исходный хук, прогон не
# блокируется. Дёшево: 1 LLM-детект (scene_tagging, temp 0) + макс 1 регенерация.
# Финанс/story (de/en Rise&Fall) сюда НЕ заходят (gate is_curiosity в k==0).
# ════════════════════════════════════════════════════════════════════════════

_MIRROR_DETECT_PROMPT = """You are a strict format classifier for "curiosity essay" video openings (warm, first-person channels like "Otra Mirada"/Spanish, "Ngẫm"/Vietnamese, and the proven "ancient humans" style). You decide ONE thing: do the FIRST 1-2 sentences pull the VIEWER into a concrete second-person scene they are EXPERIENCING — a MIRROR — rather than narrating from the outside?

mirror=TRUE — the FIRST 1-2 sentences make the VIEWER the SUBJECT, addressed as "you" / "tú" / "bạn" / "du" (dropped-pronoun second-person verbs COUNT: "Estás ahí…", "Sientes…", "Te despiertas…"), placed inside a concrete, sensory, immersive moment they are living. TWO valid flavours, BOTH true:
  (a) PRESENT MIRROR — their real ordinary now: lying in bed with the phone glow on their face, the heat rising in their cheeks, waking up with no alarm. ("You wake up when your body is ready." / "Right now, you're warm." / "You're lying in bed, the door closed.")
  (b) IMMERSIVE SCENE — a vivid "you are there" moment, even in the past, told as direct present-tense second-person sensory action: "You're walking through tall grass 100,000 years ago. You hear something move behind you. You turn around." The viewer IS the one walking, hearing, turning — they experience it firsthand.
A plain second-person QUESTION about the viewer's own real experience also counts ("¿Sientes el calor subir por el cuello ahora mismo?").

mirror=FALSE — the FIRST 1-2 sentences narrate from OUTSIDE the viewer:
- THIRD PERSON about someone else: "someone", "a man", "she", "they", "alguien", "un hombre", "một người" — an actor who is NOT the viewer. ("En una cueva en Grecia, alguien enterró…" → FALSE: it is 'someone', the viewer just watches.)
- ABSTRACT fact / statistic / definition / general "we"/humanity claim: "The human body produces…", "Todos hemos sentido…", "For 99% of history humans…".
- a DETACHED setting with NO "you" as the experiencing subject: a date, a place, a scene described in third person ("It was the year 1923…", "In a cave by firelight, a fire burned…").

KEY TEST: in the FIRST 1-2 sentences, is the grammatical subject the VIEWER ("you"), living a concrete sensory moment firsthand? YES → true (present OR vivid past-scene the viewer inhabits). If the first concrete image is a third-person actor, an abstract claim, or a setting the viewer only observes from outside → false.

Note: a vivid second-person scene set in the past is a MIRROR (true) — being immersive matters, not the era. Only switch to false when the viewer becomes an outside OBSERVER (third person) or the opening goes abstract.

Judge ONLY the first 1-2 sentences. Later sentences may turn to history/explanation — that is expected; you judge how it OPENS. Text may be Spanish or Vietnamese; judge in its own language.

Examples:
- "Estás ahí, acostado, el brillo azul del teléfono en la cara. Y de pronto aparece la frase que dijiste ayer. Sientes el calor subir desde el cuello." -> {"mirror": true, "why": "second person, viewer's own present sensory moment"}
- "Caminas entre la hierba alta hace cien mil años. El sol se pone. Oyes algo moverse detrás de ti y te giras." -> {"mirror": true, "why": "immersive second-person scene the viewer experiences firsthand, era irrelevant"}
- "En una cueva en Grecia, hace más de dos mil años, alguien enterró a un ser querido con una botella de lágrimas." -> {"mirror": false, "why": "third-person 'alguien'; the viewer only observes from outside"}
- "El cuerpo humano produce un líquido salado cuando sentimos emociones." -> {"mirror": false, "why": "abstract general claim, no viewer as subject"}

OPENING TO JUDGE:
{opener}

Return ONLY this JSON, nothing else: {"mirror": <true|false>, "why": "<one short line>"}"""


# Жёсткая mirror-инструкция, дописывается к промпту регенерации первой секции.
_MIRROR_REGEN_RULE = (
    "\n\nHARD REWRITE — PUT THE VIEWER IN THE SCENE: your previous opening narrated "
    "from the OUTSIDE (third person / an abstract fact / a detached setting the viewer "
    "only watches). The FIRST 1-2 sentences MUST make the LISTENER the SUBJECT, "
    "addressed as \"you\" (tú / bạn; dropped-pronoun second-person verbs are fine), "
    "living a concrete sensory moment FIRSTHAND. Use EITHER: (a) their real present — "
    "the small ordinary thing they are doing/feeling right now (lying in bed with the "
    "phone glow on their face, the heat rising in their cheeks, waking with no alarm); "
    "OR (b) a vivid immersive scene they inhabit, even in the past, in direct "
    "present-tense second person (\"You're walking through tall grass a hundred thousand "
    "years ago. You hear something move behind you. You turn.\"). Do NOT open in the "
    "third person (\"someone\", \"a man\", \"they\", \"alguien\"), and do NOT open with an "
    "abstract fact or a setting the viewer only observes from outside. The viewer must "
    "EXPERIENCE the opening, not watch it. Keep everything else (length, the curiosity "
    "gap, header, warm first-person tone). Rewrite the WHOLE section."
)


async def _hook_mirrors_viewer(opener: str, lang: str) -> bool | None:
    """Микросудья: открывается ли curiosity-хук ЗЕРКАЛОМ зрителя (2-е лицо, его
    настоящий момент) vs далёкая историческая/3-е-лицо/место-сцена/ролевой перенос.
    True/False, или None если судить нечего / сбой (best-effort: вызывающий трактует
    None как «не трогаем хук»). Один дешёвый LLM-вызов (scene_tagging, temp 0)."""
    opener = (opener or "").strip()
    if len(opener) < 25:
        return None
    try:
        cfg = get_model_config("scene_tagging")
    except Exception:
        return None
    prompt = _MIRROR_DETECT_PROMPT.replace("{opener}", opener[:700])
    try:
        raw = (await call_llm(
            prompt=prompt, model=cfg["primary"], temperature=0.0,
            max_tokens=cfg.get("max_tokens", 400),
            fallback_model=cfg.get("fallback"),
        )).strip()
        data = _extract_json_obj(raw)
        m = data.get("mirror")
        if isinstance(m, bool):
            logger.info("curiosity hook mirror-check (%s): mirror=%s — %s",
                        lang, m, str(data.get("why", ""))[:80])
            return m
        return None
    except Exception as e:
        logger.warning("mirror-детектор не удался (%s) — оставляю хук", e)
        return None


async def _enforce_curiosity_mirror(
    body: str, header: str, brief: str, topic: str, lang: str, model_config: dict,
) -> str:
    """Для curiosity-хука: если открытие НЕ зеркалит зрителя — ОДНА регенерация
    первой секции с жёсткой mirror-инструкцией. Best-effort: любой сбой / None /
    True → исходный body, прогон не блокируется. Макс 1 регенерация (не
    перепроверяем повторно — дёшево)."""
    try:
        text = body.split("\n", 1)[1].strip() if "\n" in body else body.strip()
        if not text:
            return body
        first = " ".join(re.split(r"(?<=[.!?…])\s", text)[:2]).strip()
        mirror = await _hook_mirrors_viewer(first, lang)
        if mirror is not False:        # True или None (неуверенно) → не трогаем
            return body
        logger.info("curiosity hook: НЕ зеркало — регенерирую первую секцию 1 раз (%s)", lang)
        lang_name = {"de": "German", "es": "Spanish",
                     "en": "English", "vi": "Vietnamese"}.get(lang, lang)
        regen_prompt = (
            f"Rewrite the OPENING (HOOK) section of a warm, first-person {lang_name} "
            f"curiosity essay about: {topic}\n"
            f"Section plan: {brief}\n\n"
            f"Current opening to rewrite:\n{text}\n\n"
            f"Keep the SAME topic, the same curiosity question and any real facts already "
            f"present — only change HOW it OPENS. Keep roughly the same length. Write 100% "
            f"in {lang_name}.\nStart with the header line exactly as given, then the "
            f"narration text. No stage directions, no meta-comments." + _MIRROR_REGEN_RULE
        )
        regen = strip_director_tail((await call_llm(
            prompt=regen_prompt, model=model_config["primary"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
            fallback_model=model_config.get("fallback"),
        )).strip())
        if not regen:
            return body
        if not regen.startswith("**["):
            regen = header + "\n" + regen
        return regen
    except Exception as e:
        logger.warning("mirror-enforce не удался (%s) — оставляю хук", e)
        return body


class _SafeDict(dict):
    """format_map без KeyError — для незаполненных плейсхолдеров шаблона."""
    def __missing__(self, key):
        return ""


async def _improve_best_hook(script: str, lang: str, topic: str | None, current_overall: float):
    """Best-of-N хука на УЛУЧШЕННОМ (плоском) тексте: генерим N вариантов из самого
    сценария → микро-судья → вставляем лучший как новое начало, но ТОЛЬКО если
    пере-оценка не уронила балл (анти-регресс). Возвращает (text, overall)."""
    try:
        cfg = get_model_config("script_hook_variants")
    except Exception:
        return script, current_overall
    n = int(cfg.get("n", 0) or 0)
    if n <= 1:
        return script, current_overall
    tmpl_path = PROMPTS_DIR / f"script-{lang}.md"
    if not tmpl_path.exists():
        return script, current_overall
    template = tmpl_path.read_text(encoding="utf-8").format_map(
        _SafeDict(topic=topic or "dieses Thema"))

    paras = [p for p in script.split("\n\n") if p.strip()]
    if len(paras) < 3:
        return script, current_overall
    # текущее начало = абзацы, пока не наберётся ~700 симв
    head, acc = [], 0
    for p in paras:
        head.append(p); acc += len(p)
        if acc >= 700:
            break
    section_hook = "\n\n".join(head)

    variants = await _generate_hook_variants(
        topic or "(siehe Story-Brief)", lang, template, script[:1800], "", n, cfg)
    best = await _pick_best_hook([section_hook] + variants, lang)
    if not best or best.strip() == section_hook.strip():
        return script, current_overall

    candidate = best.strip() + "\n\n" + "\n\n".join(paras[len(head):])
    cj = await _judge_script(candidate, lang)
    if cj["overall"] >= current_overall:
        logger.info("improve: best-of-N хук принят (%s → %s)", current_overall, cj["overall"])
        return candidate, cj["overall"]
    logger.info("improve: best-of-N хук отклонён (%s < %s)", cj["overall"], current_overall)
    return script, current_overall


def _build_targeted_improvement_prompt(script: str, lang: str, judged: dict) -> str:
    """Адресный промпт улучшения: чинит ИМЕННО то, что пометил судья (слабые
    измерения + weak_spots), а не общий шаблон."""
    weak_dims = sorted(
        [d for d in judged.get("dimensions", []) if d.get("score") is not None],
        key=lambda d: (d["score"] / d["max"]) if d.get("max") else 1.0,
    )[:3]
    dims_block = "\n".join(
        f'  - {d["label"]} (сейчас {d["score"]}/{d["max"]}): {d.get("why","")}' for d in weak_dims
    )
    spots_block = "\n".join(
        f'  - «{w.get("where","")}»: {w.get("problem","")} → {w.get("fix_hint","")}'
        for w in judged.get("weak_spots", [])
    ) or "  (нет конкретных — ориентируйся на слабые измерения выше)"
    banlist = _banlist_block(lang)

    return f"""You are a top editor for viral {lang}-language documentaries. A strict critic scored
this script. Improve it SPECIFICALLY on the weaknesses below. Keep facts/sources, but you MAY
restructure, cut and re-weight to fix these weaknesses.

OUTPUT LANGUAGE — HARD RULE: the script is in {lang}. Keep the rewrite ENTIRELY in natural,
native {lang}. Do NOT let a single word from any other language (German, English, …) slip in —
no foreign filler, no foreign source names. 100% {lang}.

WEAKEST SCORING DIMENSIONS (improve these most):
{dims_block}

CONCRETE WEAK SPOTS (fix exactly these):
{spots_block}

MANDATORY — RETENTION REBUILD (always apply, regardless of score):
- HOOK (first ~45-60s): rebuild it — (1) a verdict, or a jump into the hardest/most concrete scene; NO question, NO greeting; (2) ONE number + one line naming WHO it hit and what was at stake — threat through the real people affected, never "this affects you"; (3) one subversion line; (4) 2-4 named, UNRESOLVED cliffhangers in a stack; (5) a close — an open core question OR a knowledge promise OR one last hard fact.
- OPEN LOOPS ACROSS THE WHOLE VIDEO: resolve every loop opened in the hook later; at least 2 only AFTER the peak; open or close a loop every 2-3 minutes (incl. the 2nd half). No 2nd-half section is a mere summary — each starts with a re-hook (a new question, a twist, an unresolved consequence), never "as we have seen".
- NO FLAT NUMBER STREAKS: every key number = a person + a tangible comparison + a consequence; never two number-heavy sentences in a row; at most ~2-3 truly important numbers per minute.

RULES (targeted at the flagged weaknesses):
- FRONT-LOADING & ARC (if weak): you MAY and SHOULD restructure — pull the strongest, most shocking material to the FRONT (right after the hook), cut long background/setup drastically (max one short section, woven into the action), sharpen ONE clear peak. The first half MUST be more gripping than the second. No sag in the middle.
- OPEN LOOPS (if weak): every 2-3 min plant an open question / cliffhanger FROM THE STORY that pays off later. Natural, never mechanical ("remember this number").
- NATURALNESS (if weak): remove these AI clichés and similar entirely: {banlist}. Vary sentence rhythm (break >25-word sentences; mix short and long). At most 1-2 rhetorical questions per section. Don't repeat any word unnaturally often. Replace a clichéd ending with a concrete, resonant final thought.
- NUMBER DISCIPLINE (if facts weak): dose numbers (max ~2-3 important per minute); cut the rest or bundle into ONE vivid statement (a comparison, not a bare figure).
- SOURCES (if facts weak): state well-known facts CONFIDENTLY with a real, era- and culture-appropriate source for THIS topic (a historian, a chronicle, an archive, a named study) — do NOT hedge everything with "estimates say". Never invent sources/studies; keep real facts.
- Keep length roughly (±10%). Short TTS-friendly sentences.
- Return ONLY the improved plain narration text — no comments, no markdown.

Script:
{script}"""


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


async def _surgical_patch(script: str, lang: str, judged: dict, model_config: dict) -> str:
    """Хирургическая правка: чинит ТОЛЬКО помеченные куски (weak_spots судьи) и
    дословно-повторяющиеся предложения, не трогая остальной текст. Каждый
    проблемный абзац переписывается отдельным вызовом. Возвращает новый текст."""
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip()).lower()

    paras = [p for p in re.split(r"\n\s*\n", script) if p.strip()]
    if len(paras) < 3:
        return script

    # дубль-предложения (>=2 раза дословно) — детерминированно
    counts: dict[str, int] = {}
    for s in _SENT_SPLIT_RE.split(script):
        n = _norm(s)
        if len(n) >= 40:
            counts[n] = counts.get(n, 0) + 1
    dups = {n for n, c in counts.items() if c >= 2}

    targets: dict[int, list[str]] = {}
    if dups:
        for i, p in enumerate(paras):
            if any(_norm(s) in dups for s in _SENT_SPLIT_RE.split(p)):
                targets.setdefault(i, []).append(
                    "One sentence here repeats VERBATIM elsewhere in the script — rewrite it here "
                    "completely fresh and unique, from this section's own content, in the script's own language.")

    def _best_para(quote: str) -> int | None:
        q = _norm(quote)
        if not q:
            return None
        key = q[:40]
        for i, p in enumerate(paras):
            if key in _norm(p):
                return i
        qw = {w for w in re.findall(r"\w+", q) if len(w) > 3}
        if not qw:
            return None
        best, bi = 0.0, None
        for i, p in enumerate(paras):
            pw = {w for w in re.findall(r"\w+", _norm(p)) if len(w) > 3}
            ov = (len(qw & pw) / len(qw)) if pw else 0.0
            if ov > best:
                best, bi = ov, i
        return bi if best >= 0.5 else None

    for ws in (judged.get("weak_spots") or []):
        i = _best_para(str(ws.get("where", "")))
        if i is None:
            continue
        prob = str(ws.get("problem", "")).strip()
        fix = str(ws.get("fix_hint", "")).strip()
        targets.setdefault(i, []).append(f"Problem: {prob}. Fix: {fix}")

    if not targets:
        return script

    lang_name = {"de": "German", "es": "Spanish", "en": "English"}.get(lang, lang)

    async def _patch_one(i: int):
        para = paras[i]
        instr = "\n".join(f"- {x}" for x in targets[i])
        prompt = (
            f"Rewrite ONLY this paragraph of a {lang_name} documentary narration to fix the "
            f"listed problems. Keep ALL facts, numbers and names; keep roughly the same length; "
            f"keep it in {lang_name}; introduce NO new facts; no meta-comments, no headers.\n\n"
            f"PROBLEMS TO FIX:\n{instr}\n\nPARAGRAPH:\n{para}\n\nReturn ONLY the rewritten paragraph."
        )
        try:
            out = await call_llm(
                prompt=prompt, model=model_config["primary"],
                temperature=model_config["temperature"], max_tokens=2000,
                fallback_model=model_config.get("fallback"))
            out = strip_director_tail((out or "").strip())
            return i, (out or para)
        except Exception:
            return i, para

    import asyncio
    for i, newp in await asyncio.gather(*[_patch_one(k) for k in targets]):
        if newp and len(newp) >= 0.4 * len(paras[i]):
            paras[i] = newp
    return "\n\n".join(paras)


async def improve_script(script: str, lang: str, max_iterations: int = 3,
                         topic: str | None = None) -> str:
    """Адресное улучшение под управлением судьи:
      1) судья оценивает текст (рубрика + слабые места);
      2) если verdict=ship — стоп;
      3) строим ЦЕЛЕВОЙ промпт под слабые места + ОБЯЗАТЕЛЬНЫЙ retention-умбау
         (5-ударный хук, петли через всё видео, без плоских число-стрек);
      4) пере-оценка: если балл не вырос — откат (анти-регресс) и стоп;
      5) best-of-N хука на финальном тексте (та же наработка, что в генерации).
    Стоп-условие — на РЕАЛЬНОМ балле судьи, не на эвристике.
    """
    model_config = get_model_config("script_improvement")
    current = script
    current_judge = await _judge_script(current, lang)
    logger.info(f"improve: старт overall={current_judge['overall']} verdict={current_judge['verdict']}")

    for i in range(max_iterations):
        if current_judge["verdict"] == "ship":
            logger.info(f"improve: verdict=ship (overall={current_judge['overall']}) — стоп")
            break

        prompt = _build_targeted_improvement_prompt(_local_fix(current, lang), lang, current_judge)
        try:
            candidate = await call_llm(
                prompt=prompt,
                model=model_config["primary"],
                temperature=model_config["temperature"],
                max_tokens=model_config["max_tokens"],
                fallback_model=model_config.get("fallback"),
            )
        except Exception as e:
            logger.warning(f"improve iter {i+1}: LLM упал ({e}) — стоп")
            break

        candidate = strip_director_tail(candidate or "")
        # Length-guard: усохло >20% → бракуем кандидата и пробуем ещё (не стоп)
        if len(candidate) < 0.8 * len(current):
            logger.warning(f"improve iter {i+1}: кандидат усох ({len(candidate)} < 0.8×{len(current)}) — пропускаю")
            continue

        cand_judge = await _judge_script(candidate, lang)
        logger.info(f"improve iter {i+1}: {current_judge['overall']} → {cand_judge['overall']}")
        # Анти-регресс: принимаем только если балл вырос. НЕ сдаёмся после первой
        # неудачи — генерация стохастична, пробуем все итерации и берём лучшую.
        if cand_judge["overall"] > current_judge["overall"]:
            current, current_judge = candidate, cand_judge
        else:
            logger.info(f"improve iter {i+1}: не превзошёл — оставляю лучший, пробую ещё")

    # Хирургическая правка: чиним ТОЛЬКО помеченные судьёй weak_spots + дословные
    # повторы предложений, остальной текст не трогаем. Принимаем, если балл НЕ упал
    # (>=): убрать помеченный дефект, не ломая хорошее, — это победа даже при равном балле.
    try:
        patched = await _surgical_patch(current, lang, current_judge, model_config)
        if patched != current and len(patched) >= 0.9 * len(current):
            p_judge = await _judge_script(patched, lang)
            if p_judge["overall"] >= current_judge["overall"]:
                logger.info(f"improve: хирургическая правка принята ({current_judge['overall']} → {p_judge['overall']})")
                current, current_judge = patched, p_judge
            else:
                logger.info(f"improve: хирургическая правка отклонена ({p_judge['overall']} < {current_judge['overall']})")
    except Exception as e:
        logger.warning(f"improve: хирургическая правка не удалась ({e}) — оставляю текущий текст")

    # Финальный humanization-проход: чистит AI-штампы/ритм/повторы (естественность).
    # Анти-регресс: принимаем только если общий балл судьи не упал.
    try:
        humanized = await humanize_script(current, lang)
        if len(humanized) >= 0.9 * len(current):
            h_judge = await _judge_script(humanized, lang)
            if h_judge["overall"] >= current_judge["overall"]:
                logger.info(f"improve: humanization принят ({current_judge['overall']} → {h_judge['overall']})")
                current, current_judge = humanized, h_judge
            else:
                logger.info(f"improve: humanization отклонён ({h_judge['overall']} < {current_judge['overall']})")
    except Exception as e:
        logger.warning(f"humanization-проход не удался ({e}) — оставляю текущий текст")

    # Best-of-N для cold-open хука на финальном тексте — ТОЛЬКО story/finance.
    # Для curiosity (es/vi) хук = ЗЕРКАЛО зрителя; финанс best-of-N (verdict/mid-scene
    # jump) — его противоположность, перетёр бы зеркало. Генерация уже обеспечила зеркало
    # (_enforce_curiosity_mirror), а судья штрафует не-зеркало — так что для curiosity
    # этот проход пропускаем (и не тратим LLM на ненужные варианты).
    try:
        _is_cur = lang in ("es", "vi")
        try:
            _is_cur = str((get_channel_config(lang) or {}).get("niche", "")).startswith("curiosity")
        except Exception:
            pass
        if not _is_cur:
            current, _ = await _improve_best_hook(current, lang, topic, current_judge["overall"])
    except Exception as e:
        logger.warning(f"improve: best-of-N хука не удался ({e}) — оставляю текущий текст")

    return current


def _local_fix(script: str, lang: str) -> str:
    """Iteration 1: Local cleanup — no API call."""
    lines = script.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned.append(line)
        elif cleaned and cleaned[-1] != "":
            cleaned.append("")
    return "\n".join(cleaned)


# ── LLM-судья качества сценария (рубрика) ─────────────────────────────────────

# Рубрика: 7 критериев, сумма max = 100. Веса под приоритет клиента —
# front-loading и интересность по всей длине весят больше всего.
JUDGE_RUBRIC = [
    ("hook",       "Хук (первые 15с): шок-число/зеркало момента, identity-threat, curiosity gap",     15),
    ("frontload",  "Front-loading: самое сильное в ПЕРВОЙ половине, первая половина интереснее второй, нет провисаний", 16),
    ("engagement", "Интересность по всей длине: каждый сегмент держит (крючок/поворот/эмоция)",       14),
    ("facts",      "Факты и РЕАЛЬНЫЕ источники: конкретика, без выдуманных исследований, без перегруза числами", 15),
    ("on_brand",   "Соответствие ДНК канала из BRAND CONTRACT: тон, формат-контракт блоков, лицо повествования; дрейф жанра (тёплый curiosity → тёмный триллер/слежка/суд/крайм) = почти 0", 12),
    ("arc",        "Структура/сквозная линия: ИСТОРИЯ или CURIOSITY-ЭССЕ — оцени по фактическому формату, не требуй story-кульминации от эссе; инфо распределена", 8),
    ("loops",      "Open loops / вопросы / ре-хуки каждые 2-3 минуты",                                12),
    ("natural",    "Естественность: нет AI-штампов, короткие TTS-фразы, нет дословных повторов",        8),
]
JUDGE_SHIP_THRESHOLD = 85   # >= → ship
JUDGE_REJECT_THRESHOLD = 60  # < → reject


def _extract_json_obj(response: str) -> dict:
    """Толерантный разбор JSON-ОБЪЕКТА от LLM (по образцу _extract_scenes_json для
    массивов): снимает ```-обёртку, вырезает от первого '{' до последнего '}',
    чинит трейлинг-запятые. Reasoning-модели (R1) могут предварять JSON рассуждением."""
    import json
    t = (response or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        t = t[i:j + 1]
    t = re.sub(r",(\s*[}\]])", r"\1", t)  # трейлинг-запятые
    return json.loads(t)


def _judge_prompt(script: str, lang: str, hints: dict, channel: dict | None = None) -> str:
    rubric_lines = "\n".join(
        f'  - "{k}" (max {mx}): {label}' for k, label, mx in JUDGE_RUBRIC
    )
    ss = (channel or {}).get("script_style", {}) if isinstance(channel, dict) else {}
    brand_block = ""
    if ss:
        fb = ss.get("forbidden_phrases", []) or []
        brand_block = (
            "\nBRAND CONTRACT — the channel's DNA this script MUST stay inside (score 'on_brand' against it):\n"
            f"- TONE: {ss.get('tone','')}\n"
            f"- FORMAT / STRUCTURE: {ss.get('structure','')}\n"
            f"- NARRATION: {ss.get('narration','')}\n"
            + (f"- FORBIDDEN PHRASES/OPENERS: {', '.join(fb)}\n" if fb else "")
        )
    return f"""You are a ruthless YouTube retention editor judging a {lang}-language documentary/explainer
narration script (~{hints.get('minutes')} min spoken audio — viewers come for the CONTENT, not visuals).
Judge it for ITS OWN length and format: do NOT penalize a tight ~7-8 min curiosity/explainer essay for
being shorter than a 20-25 min story, and do NOT demand a story-style climax/collapse from an essay.
Score HONESTLY, do NOT inflate. The script is in {lang}; judge it in its own language.
LANGUAGE PURITY: if ANY word from another language (German, English, …) appears in this {lang} script,
penalize "natural" HARD and name it in weak_spots — the script must be 100% {lang}.
{brand_block}
Grounding hints (computed, do NOT score by these — judge the actual content):
- length: {hints.get('chars')} chars (~{hints.get('minutes')} min spoken)
- detected source-mentions: {hints.get('sources')}, detected numbers: {hints.get('numbers')}

Score each dimension 0..max. Be strict:
{rubric_lines}

CRITICAL judging rules:
- ON-BRAND / TONE DRIFT (critical): the script MUST stay in the channel's TONE and FORMAT in the BRAND CONTRACT above. If the genre drifts — e.g. a warm curiosity essay turns into a dark dystopian thriller, AI-surveillance, crime or courtroom drama — score "on_brand" 0-3 and make it the FIRST weak_spot. (If no BRAND CONTRACT was given, score on_brand on internal tonal consistency.)
- CURIOSITY MIRROR-HOOK (apply ONLY if the BRAND CONTRACT TONE above is warm/first-person curiosity — otherwise IGNORE this rule entirely): the hook MUST open by MIRRORING the VIEWER — the first 1-2 sentences place the viewer in their OWN present moment (second person, what the listener is doing/sensing/feeling RIGHT NOW). If such a curiosity script instead opens on a distant historical scene, another era/place, a third-person character, a role-transport ('you are in ancient Greece'), an 'imagine that…' hypothetical, or an abstract fact, score "hook" <=6 and make it the FIRST weak_spot ('хук не зеркалит зрителя — открывается историей/3-м лицом/абстракцией, а не его настоящим моментом').
- FABRICATION (red flag): a named study described as unpublished/archived/withdrawn/secret/suppressed, OR a precise % / statistic with no real institution, OR an invented researcher/institution/year, is FABRICATION. List EACH such case in fabrication_flags (quote + why) and score "facts" <=5. Do NOT reward a fabricated source for "having a number" — fabrication is worse than vagueness.
- Do NOT reward keyword-stuffing. Many "Laut Bloomberg" or many numbers do NOT mean quality.
- PENALIZE: number overload (>5 figures per spoken minute = hard to follow); AI clichés ("Es ist wichtig zu beachten", "Zusammenfassend", "En conclusión"); broken/garbled text or language-mixing; a sentence or rhetorical question repeated VERBATIM 2+ times (worst AI tell — score "natural" <=3 and quote it).
- frontload: the FIRST HALF must be stronger and more gripping than the second. If the best fact/case sits late, score frontload LOW.
- engagement: imagine a listener — does EVERY stretch keep attention, or are there flat/boring patches?

CREDIT THESE (reward, do not treat as filler — these are deliberate retention craft):
- hook: a strong cold-open OR a warm present-moment mirror that twists into a strange question is a TOP hook — score it HIGH.
- loops: reward threads opened early and PAID OFF later, plus re-hooks across the 2nd half. A teased, unresolved thread counts as an open loop even without a literal "?".
- arc: judge by the ACTUAL format — a curiosity essay (hook→evidence→big idea→loop back) is a valid arc; do not demand a story climax from it.
- facts: confidently-stated WELL-KNOWN facts (Sahlins, Blombos, founding dates) get full credit — do NOT demand citation density. Only penalize FABRICATED/implausible specifics, not a clean factual narrative.

weak_spots = the 3-6 most impactful concrete problems, each with WHERE (quote ~5-8 words or section) and a one-line fix_hint.
verdict: "ship" if overall>={JUDGE_SHIP_THRESHOLD}, "reject" if overall<{JUDGE_REJECT_THRESHOLD}, else "improve".

Return ONLY this JSON (no prose, no markdown fences):
{{"dimensions":[{{"key":"hook","label":"...","score":<int>,"max":15,"why":"<short, in Russian>"}}, ...all 8 keys in rubric order...],
"fabrication_flags":[{{"quote":"<the fabricated claim, verbatim ~5-10 words>","why":"<short RU: почему это выдумка>"}}],
"weak_spots":[{{"where":"<quote/section>","problem":"<short RU>","fix_hint":"<short RU>"}}],
"summary_ru":"<1-2 предложения по-русски: за что такой балл и что главное починить>"}}

Script:
{script}"""


def _count_verbatim_repeats(script: str) -> int:
    """Макс. число дословных повторов одного предложения/риторического вопроса
    (нормализованных, длиннее ~30 симв). Дословный повтор — худший AI-tell."""
    parts = re.split(r"(?<=[.!?…])\s+", script)
    counts: dict[str, int] = {}
    for p in parts:
        norm = re.sub(r"[^0-9a-zà-ÿñ ]", "", p.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        if len(norm) >= 30:
            counts[norm] = counts.get(norm, 0) + 1
    return max(counts.values(), default=0)


async def _judge_script(script: str, lang: str, channel: dict | None = None) -> dict:
    """LLM-судья: возвращает рубрику с overall (0-100), разбивкой, слабыми местами,
    вердиктом. overall = сумма dimension.score (прозрачно, не доверяем самооценке).
    Бренд канала (script_style) идёт в судью → штраф за оффбренд-дрейф (ось on_brand).
    Детерминированные штрафы: любая фабрикация → overall<=55 (reject); дословный
    повтор 3+ → natural<=2. При полном провале LLM/JSON — фолбэк на эвристику."""
    cfg = get_model_config("script_judge")
    if channel is None:
        try:
            channel = get_channel_config(lang)
        except Exception:
            channel = None
    # дешёвые подсказки (НЕ источник балла, только заземление судьи)
    sources = len(re.findall(
        r"(?i)(laut |según |according to |quelle|fuente|studie |estudio |study |bloomberg|reuters|handelsblatt)",
        script))
    numbers = len(re.findall(r"\b\d[\d.,]+\b", script))
    chars_per_min = {"de": 910, "es": 900, "en": 900, "vi": 1000}.get(lang, 900)
    hints = {"chars": len(script), "sources": sources, "numbers": numbers,
             "minutes": round(len(script) / chars_per_min, 1)}
    prompt = _judge_prompt(script, lang, hints, channel)
    max_rep = _count_verbatim_repeats(script)

    last_err = None
    for attempt in range(3):
        try:
            resp = await call_llm(
                prompt=prompt, model=cfg["primary"],
                temperature=cfg.get("temperature", 0.2),
                max_tokens=cfg.get("max_tokens", 8000),
                fallback_model=cfg.get("fallback"),
            )
            data = _extract_json_obj(resp)
            dims_raw = {d.get("key"): d for d in data.get("dimensions", []) if isinstance(d, dict)}
            fab_flags = [f for f in data.get("fabrication_flags", []) if isinstance(f, dict)][:8]
            dim_scores = {}
            for key, label, mx in JUDGE_RUBRIC:
                dim_scores[key] = max(0, min(mx, int(dims_raw.get(key, {}).get("score", 0))))
            # Детерминированные штрафы (не доверяем калибровке LLM):
            if fab_flags:
                dim_scores["facts"] = min(dim_scores.get("facts", 0), 5)  # любая фабрикация бьёт по фактам
            if max_rep >= 3:
                dim_scores["natural"] = min(dim_scores.get("natural", 0), 2)
            elif max_rep >= 2:
                dim_scores["natural"] = min(dim_scores.get("natural", 0), 4)
            dimensions, overall = [], 0
            for key, label, mx in JUDGE_RUBRIC:
                sc = dim_scores[key]
                overall += sc
                dimensions.append({"key": key, "label": label, "score": sc, "max": mx,
                                   "why": str(dims_raw.get(key, {}).get("why", "")).strip()})
            # Жёсткий кап за фабрикацию ВНЕ суммы осей: один выдуманный источник =
            # потеря доверия канала → не ship. (правило клиента)
            if fab_flags:
                overall = min(overall, 55)
            verdict = ("ship" if overall >= JUDGE_SHIP_THRESHOLD
                       else "reject" if overall < JUDGE_REJECT_THRESHOLD else "improve")
            return {
                "overall": overall,
                "dimensions": dimensions,
                "fabrication_flags": fab_flags,
                "weak_spots": [w for w in data.get("weak_spots", []) if isinstance(w, dict)][:6],
                "verdict": verdict,
                "summary_ru": str(data.get("summary_ru", "")).strip(),
            }
        except Exception as e:
            last_err = e
            logger.warning(f"script judge попытка {attempt+1}/3 не удалась: {e}")

    # Фолбэк: эвристика, чтобы гейт не падал
    logger.error(f"script judge провалился ({last_err}) — фолбэк на эвристику")
    heur = await _score_script(script, lang)
    return {
        "overall": int(heur),
        "dimensions": [{"key": k, "label": label, "score": None, "max": mx, "why": ""}
                       for k, label, mx in JUDGE_RUBRIC],
        "fabrication_flags": [],
        "weak_spots": [],
        "verdict": ("ship" if heur >= JUDGE_SHIP_THRESHOLD
                    else "reject" if heur < JUDGE_REJECT_THRESHOLD else "improve"),
        "summary_ru": "Судья недоступен — балл по эвристике (приблизительный).",
    }


async def assess_script(script: str, lang: str) -> dict:
    """Для гейта одобрения: ЧЕСТНЫЙ балл судьи (0-100) + рубрика с разбивкой + RU-перевод,
    чтобы клиент видел НЕ голое число, а за что балл и что чинить."""
    rubric = await _judge_script(script, lang)
    ru = ""
    try:
        ru = await call_llm(
            prompt=("Переведи этот документальный сценарий на русский — точно по смыслу, "
                    "сохраняя структуру и все числа. Только перевод, без комментариев.\n\n" + script),
            model=get_model_config("metadata")["primary"],
            temperature=0.3,
            max_tokens=16000,
        )
    except Exception as e:
        logger.warning(f"script RU-перевод не удался: {e}")
    return {"score": int(rubric["overall"]), "rubric": rubric, "script_ru": ru}


async def _score_script(script: str, lang: str) -> int:
    """Score script quality (0-100)."""
    import re
    patterns = get_patterns(lang)
    score = 50  # Base score
    
    # Forbidden AI patterns (-8 each)
    forbidden = patterns["hooks"].get("forbidden", [])
    for item in forbidden:
        if item["pattern"].lower() in script.lower():
            score -= 8
    
    # Length check
    if len(script) < 10000:
        score -= 15
    elif len(script) > 30000:
        score -= 10
    elif 14000 < len(script) < 25000:
        score += 10  # Good range
    
    # Sources: "Laut X", "Según X", "According to", "Quelle", "Fuente"
    source_patterns = r"(?i)(laut |según |according to |quelle|fuente|studie |estudio |study |bloomberg|reuters|handelsblatt)"
    source_count = len(re.findall(source_patterns, script))
    if source_count >= 6:
        score += 15
    elif source_count >= 3:
        score += 8
    elif source_count == 0:
        score -= 10
    
    # Density penalties (fallback only — fires when the LLM judge is fully down;
    # outage hygiene so a number/question-spam draft can't sneak through).
    # Aligns with the LLM judge's own ">5 figures/spoken-min = hard to follow" rule.
    cpm = {"de": 910, "es": 830, "en": 900}.get(lang, 900)
    minutes = max(len(script) / cpm, 1.0)

    # Numbers: penalize density >5 per spoken minute (was: bonus for >=15/>=8 — that
    # rewarded exactly the flat number-dumps the prompts now forbid).
    numbers = re.findall(r"\b\d[\d.,]+\b", script)
    if len(numbers) / minutes > 5:
        score -= 10

    # Question marks: penalize rhetorical-question spam >1.5 per spoken minute
    # (was: bonus for >=8 — rewarded the very "?"-spam we strip).
    questions = script.count("?")
    if questions / minutes > 1.5:
        score -= 5
    
    # First sentence should contain a number or shocking claim
    first_line = script.strip().split("\n")[0] if script.strip() else ""
    if re.search(r"\d", first_line):
        score += 5
    
    return max(0, min(100, score))


def _build_source_context(transcripts: list[dict] | None, lang: str) -> str:
    """
    Build the source context block to inject into the script prompt.
    Returns empty string when no transcripts provided.
    """
    if not transcripts:
        return ""

    labels = {
        "de": (
            "## Quell-Kontext: Transkript eines bewährten, erfolgreichen Videos\n\n"
            "Dieses Transkript ist eine BEWÄHRTE Vorlage (hohe Watch-Time). Nutze es ZWEIFACH:\n"
            "1. FAKTEN: übernimm die ECHTEN Zahlen, Daten, Namen, Studien, Orte und Beispiele "
            "daraus (sie sind verifiziert — erfinde NICHTS dazu).\n"
            "2. STRUKTUR: folge demselben Aufbau — öffne mit dem Zuschauer in einer konkreten "
            "Szene (du/dein Moment), wende dich dann der seltsamen Frage zu, belege mit den "
            "echten benannten Funden, nimm den Einwand des Zuschauers vorweg, steigere konkrete "
            "Fakten, und schließe mit einer Wendung, die auf das heutige Leben des Zuschauers "
            "zurückführt.\n"
            "ABER: schreibe ein KOMPLETT ORIGINALES Skript mit EIGENEN Worten. Übernimm KEINEN "
            "Satz wörtlich (Plagiat/Copyright/YouTube-Dedup). Gleiche Fakten & Bogen, neue Sprache.\n\n"
        ),
        "es": (
            "## Contexto fuente: Transcripción de un video probado y exitoso\n\n"
            "Esta transcripción es una PLANTILLA PROBADA (mucha retención). Úsala de DOS formas:\n"
            "1. HECHOS: toma los datos REALES — números, fechas, nombres, estudios, lugares y "
            "ejemplos concretos que aparecen (están verificados; NO inventes nada nuevo).\n"
            "2. ESTRUCTURA: sigue el mismo recorrido — abre con el espectador dentro de una escena "
            "concreta (tú / su momento, en presente o una escena vívida que él vive), gira hacia la "
            "pregunta extraña, respáldala con los hallazgos reales con nombre, anticipa la objeción "
            "del espectador ('quizás piensas que…'), escala hechos concretos fascinantes, y cierra "
            "con un giro que vuelve a la vida actual del espectador.\n"
            "PERO: escribe un guión TOTALMENTE ORIGINAL con TUS palabras. NO copies ninguna frase "
            "literalmente (plagio/copyright/dedup de YouTube). Mismos hechos y arco, lenguaje nuevo.\n\n"
        ),
        "en": (
            "## Source Context: Transcript of a proven, successful video\n\n"
            "This transcript is a PROVEN template (high retention). Use it in TWO ways:\n"
            "1. FACTS: take the REAL numbers, dates, names, studies, places and concrete examples "
            "in it (they are verified — do NOT invent new ones).\n"
            "2. STRUCTURE: follow the same arc — open with the viewer inside a concrete scene "
            "(you / their moment), turn to the strange question, back it with the real named "
            "findings, anticipate the viewer's objection, escalate concrete fascinating facts, and "
            "close on a turn that loops back to the viewer's life today.\n"
            "BUT: write a COMPLETELY ORIGINAL script in YOUR OWN words. Do NOT copy any sentence "
            "verbatim (plagiarism/copyright/YouTube dedup). Same facts & arc, new language.\n\n"
        ),
    }
    header = labels.get(lang, labels["en"])

    parts = [header]
    for i, src in enumerate(transcripts, 1):
        title = src.get("title", src.get("url", f"Video {i}"))
        transcript = src.get("transcript", "")
        parts.append(f"### Источник {i}: {title}\n\n{transcript}\n")

    return "\n".join(parts)
