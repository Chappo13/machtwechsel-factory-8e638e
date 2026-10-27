"""Письменный стандарт сценария: бинарные правила (чек-лист) вместо нечётких оценок 1-10.

Владелец (17.10): нечёткие шкалы критика упираются в потолок 7-8 («не завышай»), а реальные хиты на этой
же шкале получают 5-7. Поэтому рядом со шкалами критик проверяет сценарий по ЗАПИСАННЫМ правилам
(prompts/script_checklist.md, пункты 1-24 + прошлые решения владельца). Каждое правило бинарное
(выполнено / нет), имеет severity (critical | major | minor), определение в одну строку, цитату-доказательство
и однострочный fix. Результат кладётся в scorecard["rules"] и участвует в вердикте (critic.evaluate_verdict,
дорожка «по правилам»).

Два способа проверки:
  а) КОД (детерминированно, по тексту script.json): длина и содержание хука, число пунктов, вопросы к зрителю,
     плотность риторики, длина глав, мостики, запрещённые открытия, «Представьте», призыв подписаться, оговорки;
  б) LLM (ОДИН вызов, Sonnet через ask_json, кэш в llm_cache.json): парадокс с мерой в хуке, сквозная мысль,
     объяснение новых имён, человек/сцена в главах, честность легенд, первый мини-payoff, отсутствие
     противоречий. Каждый ответ: {id, pass, evidence: дословная цитата, fix: одна строка}.
Сбой LLM -> rules = None, вердикт считается по прежним дорожкам. Модуль никогда не бросает.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from .util import ask_json, load_prompt

# ---------- реестр правил (единственный источник: промпт, дашборд и доки берут отсюда) ----------

RULES = [
    # --- код ---
    {"id": "hook_length", "severity": "major", "kind": "code", "ref": "п.1, 18",
     "title": "Хук 60-170 слов",
     "text": "Хук (hook) длиной 60-170 слов: короче нет парадокса и обещания, длиннее зритель уходит до сути."},
    {"id": "hook_measure", "severity": "major", "kind": "code", "ref": "п.4, 18",
     "title": "Число или мера в первых трёх предложениях хука",
     "text": "В первых трёх предложениях хука есть число или мера: числительное (две, пятнадцать, двадцать миллиардов, 800) "
             "или единица измерения (метры, тонны, градусы, этажи); порядковые («девятнадцатого века») не считаются."},
    {"id": "hook_count_word", "severity": "major", "kind": "code", "ref": "п.18, 20",
     "title": "Число пунктов названо в хуке",
     "text": "Если главы пронумерованы («Точка 1», «Находка 3», «Часть 2»), в хуке названо общее число пунктов "
             "(«семь мест», «пять находок»); без нумерации глав правило не применяется."},
    {"id": "viewer_questions", "severity": "major", "kind": "code", "ref": "п.21",
     "title": "3-6 призывов к зрителю, один в финале",
     "text": "3-6 прямых обращений к зрителю с призывом ответить («как вы думаете», «напишите», «оставьте», "
             "«в комментариях»; пара «вопрос + призыв» считается за одно), одно из них в финале (outro или последние 6 предложений)."},
    {"id": "rhetorical_density", "severity": "minor", "kind": "code", "ref": "п.21",
     "title": "Риторика не чаще 6 на 1000 слов",
     "text": "Риторических вопросов (вопросительные предложения вне призывов к зрителю) не больше 6 на 1000 слов."},
    {"id": "chapter_length", "severity": "minor", "kind": "code", "ref": "п.7, 16",
     "title": "Главы первых 10 минут не длиннее 380 слов",
     "text": "Ни одна глава, начинающаяся в первых 10 минутах озвучки, не длиннее 380 слов."},
    {"id": "bridges", "severity": "major", "kind": "code", "ref": "п.13, 22",
     "title": "Мостик в конце каждой главы",
     "text": "Каждая глава, кроме последней, заканчивается мостиком: вопросом или словами перехода («но», «а теперь», "
             "«следующая», «дальше», «прежде чем») в последних трёх предложениях; эвристика допускает один промах."},
    {"id": "banned_openers", "severity": "critical", "kind": "code", "ref": "п.1; script.md",
     "title": "Нет мета-открытий",
     "text": "В хуке и в начале глав нет мета-открытий: «в этом видео», «сегодня мы разберём», «привет», «добро пожаловать», «дорогие друзья»."},
    {"id": "predstavte_limit", "severity": "minor", "kind": "code", "ref": "playbook",
     "title": "«Представьте» не больше двух раз",
     "text": "«Представьте» (и «вообразите») встречается в ролике не больше двух раз."},
    {"id": "outro_subscribe", "severity": "major", "kind": "code", "ref": "п.17",
     "title": "Призыв подписаться в финале",
     "text": "В outro есть одна живая фраза-приглашение подписаться на канал или поставить лайк."},
    {"id": "hedging_run", "severity": "minor", "kind": "code", "ref": "п.11",
     "title": "Не больше двух оговорок подряд",
     "text": "Не больше двух предложений подряд начинаются с оговорки («возможно», «считается», «учёные предполагают», «источники расходятся»)."},
    # --- LLM (один вызов) ---
    {"id": "hook_paradox", "severity": "critical", "kind": "llm", "ref": "п.1, 18",
     "title": "Хук-парадокс с мерой",
     "text": "В первых трёх предложениях хука одновременно: (а) ясно, о чём ролик, (б) парадокс или трещина в официальной версии, "
             "(в) конкретная мера, число или сверхстепень; живой человек или сцена не заменяют (б) и (в)."},
    {"id": "through_line", "severity": "major", "kind": "llm", "ref": "п.14, 19",
     "title": "Сквозная мысль в хуке и финале",
     "text": "Есть одна сквозная мысль в одну фразу: она звучит в хуке и эхом возвращается в финале (outro или последняя глава), а финал не сводится к пересказу фактов."},
    {"id": "terms_explained", "severity": "major", "kind": "llm", "ref": "п.8",
     "title": "Новые имена и термины объяснены",
     "text": "Каждое новое имя, термин или топоним при первом упоминании объяснено одной фразой (общеизвестное школьнику не в счёт); "
             "необъяснённых не больше трёх на весь ролик, нарушители перечислены."},
    {"id": "chapter_scene", "severity": "major", "kind": "llm", "ref": "п.9, 16",
     "title": "В каждой главе человек или сцена",
     "text": "В каждой главе (кроме коротких до 100 слов) есть живой человек (имя или роль) или конкретная сцена, а не только пересказ фактов."},
    {"id": "legends_honest", "severity": "critical", "kind": "llm", "ref": "п.10, 24",
     "title": "Легенды подписаны, выдумок нет",
     "text": "Легенды, слухи и спорные версии поданы как рассказ или версия («по преданию», «говорят», «есть гипотеза»), установленный факт отделён от них; "
             "нет выдуманных точных дат, «очевидцев», цитат и находок, нет тона «наука скрывает»."},
    {"id": "first_payoff", "severity": "major", "kind": "llm", "ref": "п.16",
     "title": "Первый мини-payoff до 3-й минуты",
     "text": "Первый мини-payoff (ответ на малый вопрос, находка, поворот, частичное объяснение загадки) наступает в первых ~3 минутах озвучки, считая с начала хука."},
    {"id": "no_contradiction", "severity": "major", "kind": "llm", "ref": "п.6, 12",
     "title": "Нет противоречий между частями",
     "text": "Нет противоречий между частями: одно число, дата или имя названо по-разному, вывод одной главы опровергнут другой, обещание хука нарушено финалом."},
]
RULE_BY_ID = {r["id"]: r for r in RULES}
CODE_IDS = [r["id"] for r in RULES if r["kind"] == "code"]
LLM_IDS = [r["id"] for r in RULES if r["kind"] == "llm"]
SEV_ORDER = {"critical": 0, "major": 1, "minor": 2}
SEV_LABEL = {"critical": "критично", "major": "важно", "minor": "мелочь"}

# пороги кода (в одном месте, чтобы тесты и доки ссылались на них)
HOOK_MIN_WORDS, HOOK_MAX_WORDS = 60, 170
VIEWER_MIN, VIEWER_MAX = 3, 6
VIEWER_FINAL_SENTENCES = 6          # «в финале» = outro или последние 6 предложений (в чек-листе п.17: вопрос, подписка, тизер)
RHETORICAL_MAX_PER_1000 = 6.0
CHAPTER_MAX_WORDS = 380
BRIDGE_ALLOWED_MISSES = 1
BRIDGE_TAIL_SENTENCES = 3           # мостик может быть абзацем из 2-3 предложений («А для X… Скоро он… И там…»)
PREDSTAVTE_MAX = 2
HEDGE_RUN_MAX = 2
# LLM: сколько доказательных цитат из текста обязательно у ПРОЙДЕННОГО правила (иначе пасс не засчитывается)
EVIDENCE_REQUIRED = {"hook_paradox": 1, "through_line": 2, "first_payoff": 1}
TERMS_MAX_OFFENDERS = 3


# ---------- текстовые помощники ----------

def _norm(s: str) -> str:
    return str(s or "").lower().replace("ё", "е")


def words_in(text: str) -> int:
    return len(str(text or "").split())


def split_sentences(text: str) -> list[str]:
    """Предложения по . ! ? … (закрывающие кавычки/скобки остаются при предложении). Пустые отбрасываются."""
    out = []
    for m in re.finditer(r"[^.!?…]+(?:[.!?…]+[\"»”)]*|$)", str(text or "")):
        s = m.group(0).strip()
        if s and re.search(r"\w", s):
            out.append(s)
    return out


def script_blocks(script: dict) -> list[dict]:
    """[{kind: hook|section|outro, title, text}] в порядке озвучки."""
    script = script if isinstance(script, dict) else {}
    out = [{"kind": "hook", "title": "hook", "text": str(script.get("hook") or "")}]
    for s in script.get("sections") or []:
        if isinstance(s, dict):
            out.append({"kind": "section", "title": str(s.get("title") or s.get("id") or "глава"), "text": str(s.get("text") or "")})
    out.append({"kind": "outro", "title": "outro", "text": str(script.get("outro") or "")})
    return out


def _all_sentences(blocks: list[dict]) -> list[dict]:
    """Все предложения ролика с привязкой к блоку: [{i, block, kind, text}]."""
    out = []
    for bi, b in enumerate(blocks):
        for s in split_sentences(b["text"]):
            out.append({"i": len(out), "block": bi, "kind": b["kind"], "text": s})
    return out


_NUM_TOKENS = frozenset("""
два две двух двум двумя двое трое три трех трем тремя четыре четырех четырем четырьмя пять пяти пятью шесть шести шестью
семь семи восемь восьми восемью девять девяти девятью десять десяти десятью десятки десятков десятка
одиннадцать одиннадцати двенадцать двенадцати тринадцать тринадцати четырнадцать четырнадцати пятнадцать пятнадцати
шестнадцать шестнадцати семнадцать семнадцати восемнадцать восемнадцати девятнадцать девятнадцати
двадцать двадцати тридцать тридцати сорок сорока пятьдесят пятидесяти шестьдесят шестидесяти семьдесят семидесяти
восемьдесят восьмидесяти девяносто девяноста
сто ста двести двухсот триста трехсот четыреста четырехсот пятьсот пятисот шестьсот шестисот семьсот семисот
восемьсот восьмисот девятьсот девятисот сотни сотен сотню сотнями полтора полторы полутора
""".split())
_NUM_PREFIX_RE = re.compile(r"(?:тысяч|миллион|миллиард|триллион)\w*")
_UNIT_RE = re.compile(r"(?:метр(?:а|ов|у|ом|е|ы|ами|ах)?|километр(?:а|ов|у|ом|е|ы|ами|ах)?|миллиметр\w*|сантиметр\w*|"
                      r"тонн(?:а|ы|у|е|ой|ами|ах)?|килограмм\w*|градус\w*|этаж\w*|процент\w*|гектар\w*|литр(?:а|ов|ы)?|"
                      r"миль|мили|миля|км|кг)")
_TOKEN_RE = re.compile(r"[a-zа-я0-9]+")


def has_number_or_measure(text: str) -> bool:
    """Есть числительное (слово или цифра) либо единица измерения. Порядковые («девятнадцатого») не считаются."""
    for t in _TOKEN_RE.findall(_norm(text)):
        if any(ch.isdigit() for ch in t) or t in _NUM_TOKENS or _NUM_PREFIX_RE.fullmatch(t) or _UNIT_RE.fullmatch(t):
            return True
    return False


_COUNT_FORMS = {
    2: "два две двух двум двумя", 3: "три трех трем тремя", 4: "четыре четырех четырем четырьмя",
    5: "пять пяти пятью", 6: "шесть шести шестью", 7: "семь семи", 8: "восемь восьми восемью",
    9: "девять девяти девятью", 10: "десять десяти десятью", 11: "одиннадцать одиннадцати",
    12: "двенадцать двенадцати", 13: "тринадцать тринадцати", 14: "четырнадцать четырнадцати",
    15: "пятнадцать пятнадцати", 16: "шестнадцать шестнадцати", 17: "семнадцать семнадцати",
    18: "восемнадцать восемнадцати", 19: "девятнадцать девятнадцати", 20: "двадцать двадцати",
}
_ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четверт": 4, "пят": 5, "шест": 6,
             "седьм": 7, "восьм": 8, "девят": 9, "десят": 10, "одиннадцат": 11, "двенадцат": 12}
_NUMBERED_TITLE_RE = re.compile(
    r"^\s*(?:точка|место|находка|пункт|объект|загадка|тайна|чудо|технология|случай|часть|глава|история|сооружение|"
    r"артефакт|постройка|город|№|#)\s*[№#]?\s*(\d{1,2})\b", re.I)
_NUMBERED_TEXT_RE = re.compile(
    r"^\s*(?:точка|место|находка|пункт|объект|загадка|часть|глава)\s+(перв|втор|трет|четверт|пят|шест|седьм|восьм|девят|десят|одиннадцат|двенадцат)",
    re.I)


def numbered_sections(blocks: list[dict]) -> list[int]:
    """Номера пунктов у пронумерованных глав («Точка 1», «Находка 3», «Часть вторая» в начале текста)."""
    nums = []
    for b in blocks:
        if b["kind"] != "section":
            continue
        m = _NUMBERED_TITLE_RE.match(b["title"])
        if m:
            nums.append(int(m.group(1)))
            continue
        m = _NUMBERED_TEXT_RE.match(_norm(b["text"]))
        if m:
            stem = m.group(1)
            nums.append(next((v for k, v in _ORDINALS.items() if stem.startswith(k)), 0) or 0)
    return [n for n in nums if n > 0]


_CALL_RE = re.compile(
    r"\b(?:напишите|напиши|оставьте|оставь|расскажите|поделитесь|ответьте|пишите|сообщите)\b|в комментари|под видео|под этим видео|"
    r"под роликом|как вы думаете|как думаете|что вы думаете|что думаете|как по-вашему|по-вашему|по вашему мнению|"
    r"как вы считаете|как считаете|согласны ли вы|откуда вы смотрите")


def viewer_call_groups(sents: list[dict]) -> list[list[int]]:
    """Группы подряд идущих предложений-призывов к зрителю: пара «вопрос + призыв» = один призыв
    (вопросительное предложение прямо перед призывом входит в его группу)."""
    hit = {s["i"] for s in sents if _CALL_RE.search(_norm(s["text"]))}
    for s in sents:
        if s["i"] in hit and s["i"] > 0 and "?" in sents[s["i"] - 1]["text"]:
            hit.add(s["i"] - 1)
    groups, cur = [], []
    for i in sorted(hit):
        if cur and cur[-1] == i - 1:
            cur.append(i)
        else:
            if cur:
                groups.append(cur)
            cur = [i]
    if cur:
        groups.append(cur)
    return groups


_BRIDGE_RE = re.compile(r"\bно\b|(?:^|[.!?…,;:—»] *)а\s|следующ|а теперь|дальше|прежде чем|впереди|вот что|а вот")
_BANNED_RE = re.compile(
    r"в этом видео|в этом ролике|в сегодняшнем видео|сегодня мы (?:разберем|поговорим|расскажем|узнаем|посмотрим|проверим|выясним|изучим|обсудим)|"
    r"\bпривет\b|здравствуйте|добро пожаловать|дорогие друзья|уважаемые зрители|(?:^|\s)друзья[,!]")
_PREDSTAVTE_RE = re.compile(r"\b(?:представьте|представим|вообразите|вообразим)\b")
_SUBSCRIBE_RE = re.compile(r"подпиш|подписк|лайк|колокольчик")
_HEDGE_RE = re.compile(
    r"^[\W_]*(?:возможно|вероятно|видимо|похоже|скорее всего|предположительно|по-видимому|не исключено|может быть|якобы|считается|"
    r"принято (?:считать|думать)|по некоторым данным|по одной из версий|по мнению|"
    r"учены[ех] (?:предполагают|считают|полагают|спорят|не уверены)|историки (?:считают|спорят|предполагают|не уверены)|"
    r"записей нет|источники расходятся|не установлено|точно неизвестно|достоверно неизвестно|неизвестно)")


def _quote(s: str, n: int = 140) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _item(rid: str, ok: bool, evidence: str = "", fix: str = "", na: bool = False) -> dict:
    r = RULE_BY_ID[rid]
    return {"id": rid, "severity": r["severity"], "kind": r["kind"], "title": r["title"], "definition": r["text"],
            "pass": bool(ok), "evidence": _quote(evidence, 300), "fix": "" if ok else _quote(fix, 400), "na": bool(na)}


# ---------- правила, проверяемые кодом ----------

def code_rules(script: dict, open10_words: int | None = None) -> list[dict]:
    """Детерминированные правила по тексту script. open10_words — сколько слов озвучивается за первые 10 минут
    (по умолчанию из util.opening_words(10); при сбое 1100)."""
    if open10_words is None:
        try:
            from .util import opening_words
            open10_words = opening_words(10)
        except Exception:  # noqa: BLE001
            open10_words = 1100
    blocks = script_blocks(script)
    sents = _all_sentences(blocks)
    hook = blocks[0]["text"]
    sections = [b for b in blocks if b["kind"] == "section"]
    outro = blocks[-1]["text"]
    total_words = sum(words_in(b["text"]) for b in blocks)
    out: list[dict] = []

    # hook_length
    hw = words_in(hook)
    ok = HOOK_MIN_WORDS <= hw <= HOOK_MAX_WORDS
    out.append(_item("hook_length", ok, f"{hw} слов",
                     f"Хук {hw} слов, нужно {HOOK_MIN_WORDS}-{HOOK_MAX_WORDS}: " + (
                         "добавь парадокс с мерой и обещание ролика" if hw < HOOK_MIN_WORDS
                         else "оставь парадокс, меру и обещание, лишние подробности убери")))

    # hook_measure
    hook_sents = split_sentences(hook)[:3]
    first3 = " ".join(hook_sents)
    ok = has_number_or_measure(first3)
    out.append(_item("hook_measure", ok, _quote(first3), "В первых трёх предложениях хука назови число или меру "
                     "(метры, тонны, годы, суммы): сначала мера и сравнение, потом число"))

    # hook_count_word
    nums = numbered_sections(blocks)
    if len(nums) >= 3:
        n = max(nums)
        forms = set(_COUNT_FORMS.get(n, "").split())
        toks = set(_TOKEN_RE.findall(_norm(hook)))
        if forms:
            ok = bool(forms & toks) or str(n) in toks
        else:
            ok = has_number_or_measure(hook)
        out.append(_item("hook_count_word", ok, f"пронумерованных глав: {len(nums)}, последний номер {n}",
                         f"Главы пронумерованы (до {n}), назови в хуке общее число пунктов (например, «{_COUNT_FORMS.get(n, str(n)).split()[0]} мест»)"))
    else:
        out.append(_item("hook_count_word", True, "главы не пронумерованы: правило не применяется", na=True))

    # viewer_questions (+ rhetorical_density использует те же группы)
    groups = viewer_call_groups(sents)
    outro_idx = {s["i"] for s in sents if s["kind"] == "outro"}
    last_idx = {s["i"] for s in sents[-VIEWER_FINAL_SENTENCES:]}
    final_ok = any(set(g) & (outro_idx | last_idx) for g in groups)
    count_ok = VIEWER_MIN <= len(groups) <= VIEWER_MAX
    ev = f"призывов к зрителю: {len(groups)}, в финале: {'да' if final_ok else 'нет'}"
    if groups:
        ev += "; напр.: «" + _quote(sents[groups[-1][-1]]["text"], 80) + "»"
    fixes = []
    if len(groups) < VIEWER_MIN:
        fixes.append(f"Добавь прямые вопросы-призывы к зрителю («Как вы думаете…? Напишите свою версию»): сейчас {len(groups)}, нужно {VIEWER_MIN}-{VIEWER_MAX}")
    elif len(groups) > VIEWER_MAX:
        fixes.append(f"Призывов к зрителю {len(groups)}, оставь не больше {VIEWER_MAX}")
    if not final_ok:
        fixes.append("в финале нужен один призыв ответить («Напишите, откуда вы смотрите»)")
    out.append(_item("viewer_questions", count_ok and final_ok, ev, "; ".join(fixes)))

    # rhetorical_density
    in_group = {i for g in groups for i in g}
    rhet = [s for s in sents if "?" in s["text"] and s["i"] not in in_group]
    dens = len(rhet) / (total_words / 1000.0) if total_words else 0.0
    out.append(_item("rhetorical_density", dens <= RHETORICAL_MAX_PER_1000,
                     f"риторических вопросов: {len(rhet)} ({dens:.1f} на 1000 слов)",
                     f"Риторических вопросов {len(rhet)} ({dens:.1f} на 1000 слов), допустимо до {RHETORICAL_MAX_PER_1000:g}: "
                     "убери вопрос-связку между фактами, оставь вопросы в конце глав"))

    # chapter_length
    long_ch, pos = [], words_in(hook)
    for b in sections:
        w = words_in(b["text"])
        if pos < open10_words and w > CHAPTER_MAX_WORDS:
            long_ch.append((b["title"], w))
        pos += w
    out.append(_item("chapter_length", not long_ch,
                     "; ".join(f"«{_quote(t, 40)}» {w} слов" for t, w in long_ch) or f"все главы первых {open10_words} слов не длиннее {CHAPTER_MAX_WORDS}",
                     "Разбей главу на две или убери лишнюю деталь: " + "; ".join(f"«{_quote(t, 40)}» {w} слов" for t, w in long_ch)))

    # bridges
    missing = []
    for k, b in enumerate(sections[:-1]):
        tail = split_sentences(b["text"])[-BRIDGE_TAIL_SENTENCES:]
        low = _norm(" ".join(tail))
        if not ("?" in low or _BRIDGE_RE.search(low)):
            missing.append(b["title"])
    out.append(_item("bridges", len(missing) <= BRIDGE_ALLOWED_MISSES,
                     f"глав без мостика: {len(missing)} из {max(0, len(sections) - 1)}" + (
                         ": " + "; ".join(f"«{_quote(t, 40)}»" for t in missing) if missing else ""),
                     "Закончи главу новым вопросом или контрастом, который тянет к следующей: " + "; ".join(f"«{_quote(t, 40)}»" for t in missing)))

    # banned_openers
    openers = [hook] + [" ".join(split_sentences(b["text"])[:2]) for b in sections]
    hits = []
    for t in openers:
        m = _BANNED_RE.search(_norm(t))
        if m:
            hits.append(m.group(0).strip())
    out.append(_item("banned_openers", not hits, ("найдено: " + ", ".join(f"«{h}»" for h in hits)) if hits else "мета-открытий нет",
                     "Убери мета-открытие (" + ", ".join(f"«{h}»" for h in hits) + "): начни с факта или сцены"))

    # predstavte_limit
    full = _norm(" ".join(b["text"] for b in blocks))
    n_pr = len(_PREDSTAVTE_RE.findall(full))
    out.append(_item("predstavte_limit", n_pr <= PREDSTAVTE_MAX, f"«представьте/вообразите»: {n_pr}",
                     f"«Представьте» {n_pr} раз, допустимо до {PREDSTAVTE_MAX}: замени на прямое описание сцены"))

    # outro_subscribe (нет outro -> последняя глава)
    tail_text = outro if outro.strip() else (sections[-1]["text"] if sections else "")
    m = _SUBSCRIBE_RE.search(_norm(tail_text))
    ev = "в финале есть приглашение подписаться/поставить лайк" if m else "в финале нет приглашения подписаться"
    out.append(_item("outro_subscribe", bool(m), ev, "В последних предложениях outro добавь одну живую фразу: подпишитесь на канал и "
                     "поставьте лайк, если было интересно (один раз, без шаблона «колокольчик»), затем тизер следующего видео"))

    # hedging_run
    run = best = 0
    best_end = -1
    for s in sents:
        if _HEDGE_RE.match(_norm(s["text"])):
            run += 1
            if run > best:
                best, best_end = run, s["i"]
        else:
            run = 0
    ev = f"подряд оговорок в начале предложений: {best}"
    if best > HEDGE_RUN_MAX:
        ev += "; напр.: «" + _quote(sents[best_end]["text"], 80) + "»"
    out.append(_item("hedging_run", best <= HEDGE_RUN_MAX, ev,
                     f"{best} предложения подряд начинаются с оговорки: оставь одну, остальные скажи прямо"))
    return out


# ---------- правила, которые судит LLM ----------

def rules_text_for_llm(script: dict) -> str:
    """Весь сценарий с отметками позиции (слова от начала озвучки) для LLM."""
    blocks = script_blocks(script)
    pos, parts = 0, []
    for b in blocks:
        w = words_in(b["text"])
        if not w:
            continue
        label = {"hook": "ХУК", "outro": "ФИНАЛ (outro)"}.get(b["kind"], f"ГЛАВА «{b['title']}»")
        parts.append(f"[{label}] (слова {pos + 1}-{pos + w}, {w} слов)\n{b['text'].strip()}")
        pos += w
    return "\n\n".join(parts)


def llm_prompt(script: dict) -> str:
    try:
        from .util import opening_words
        payoff_words = opening_words(3)
    except Exception:  # noqa: BLE001
        payoff_words = 340
    rules = "\n".join(f"{i}. {r['id']} [{r['severity']}]: {r['text']}"
                      for i, r in enumerate((RULE_BY_ID[x] for x in LLM_IDS), 1))
    return load_prompt("script_rules.md", SCRIPT=rules_text_for_llm(script), RULES=rules,
                       IDS=", ".join(LLM_IDS), PAYOFF_WORDS=payoff_words, TERMS_MAX=TERMS_MAX_OFFENDERS)


def _coerce_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        t = v.strip().casefold()
        if t in ("true", "yes", "да", "1", "pass", "выполнено"):
            return True
        if t in ("false", "no", "нет", "0", "fail", "не выполнено"):
            return False
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    return None


def _fragments(evidence: str) -> list[str]:
    """Цитаты из поля evidence: сначала всё в «», иначе деление по | ; … и переводам строки (метки «хук:» отбрасываются)."""
    ev = str(evidence or "")
    frags = re.findall(r"«([^»]+)»", ev)
    if not frags:
        for p in re.split(r"\||;|…|\.\.\.|\n", ev):
            p = p.strip()
            m = re.match(r"^([^:«]{1,14}):\s*(.+)$", p)
            frags.append(m.group(2) if m else p)
    return [f.strip(" \"'“”«».,;") for f in frags if f.strip()]


def _plain(s: str) -> str:
    return " ".join(_TOKEN_RE.findall(_norm(s)))


def quotes_found(evidence: str, script_text: str) -> int:
    """Сколько цитат из evidence (минимум 3 слова) дословно есть в тексте сценария (без учёта регистра, ё и знаков)."""
    hay = _plain(script_text)
    n = 0
    for f in _fragments(evidence):
        p = _plain(f)
        if len(p.split()) >= 3 and p in hay:
            n += 1
    return n


def normalize_llm_rules(raw, script_text: str = "") -> list[dict] | None:
    """Ответ LLM -> полные пункты правил (в порядке LLM_IDS). Нет какого-то правила / не dict -> None.
    Пройденное правило из EVIDENCE_REQUIRED без проверяемой цитаты в тексте считается проваленным. Не бросает."""
    items = raw.get("rules") if isinstance(raw, dict) else raw
    if isinstance(items, dict):  # {"hook_paradox": {...}, ...}
        items = [dict(v, id=k) for k, v in items.items() if isinstance(v, dict)]
    if not isinstance(items, list):
        return None
    got = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = str(it.get("id") or "").strip()
        ok = _coerce_bool(it.get("pass", it.get("passed")))
        if rid in LLM_IDS and ok is not None and rid not in got:
            ev, fx = it.get("evidence", ""), it.get("fix", "")
            got[rid] = (ok, ev if isinstance(ev, str) else json.dumps(ev, ensure_ascii=False),
                        fx if isinstance(fx, str) else "")
    if any(r not in got for r in LLM_IDS):
        return None
    out = []
    for rid in LLM_IDS:
        ok, ev, fx = got[rid]
        need = EVIDENCE_REQUIRED.get(rid, 0)
        if ok and need and script_text and quotes_found(ev, script_text) < need:
            ok = False
            fx = "нет проверяемой цитаты-доказательства в тексте: " + (fx or "приведи в тексте явную фразу, которая выполняет правило")
            ev = (ev + " [цитата не найдена в тексте]").strip()
        if not ok and not fx.strip():
            fx = "Исправь по определению правила: " + RULE_BY_ID[rid]["title"]
        out.append(_item(rid, ok, ev, fx))
    return out


# ---------- сборка ----------

def summarize(items: list[dict]) -> dict:
    """{passed, total, critical_failed, major_failed, minor_failed, items}; правила «не применимо» (na) не считаются."""
    app = [i for i in items if not i.get("na")]
    failed = [i for i in app if not i["pass"]]

    def ids(sev):
        return [i["id"] for i in failed if i["severity"] == sev]
    return {"passed": len(app) - len(failed), "total": len(app), "critical_failed": ids("critical"),
            "major_failed": ids("major"), "minor_failed": ids("minor"), "items": items}


def _cache_get(path, key):
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(key) if path is not None and path.exists() else None
    except (OSError, ValueError, AttributeError):
        return None


def _cache_put(path, key, value) -> None:
    if path is None:
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
        data[key] = value
        tmp = path.with_name(path.name + ".rules.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except (OSError, ValueError):
        pass


def llm_rules(script: dict, cache_path=None) -> tuple[list[dict] | None, str | None]:
    """ОДИН вызов LLM на все судейские правила; кэш llm_cache.json (ключ rules:<sha1 промпта>). Не бросает."""
    try:
        prompt = llm_prompt(script)
        key = "rules:" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()
        data = _cache_get(cache_path, key)
        if data is None:
            data, _ = ask_json(prompt, timeout=900)
            items = normalize_llm_rules(data, rules_text_for_llm(script))
            if items is not None:
                _cache_put(cache_path, key, data)
        else:
            items = normalize_llm_rules(data, rules_text_for_llm(script))
        if items is None:
            return None, "невалидный ответ проверки правил"
        return items, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"[:200]


def evaluate(script: dict, job: dict | None = None, cache_path=None, open10_words: int | None = None) -> tuple[dict | None, str | None]:
    """(rules|None, error|None). Сбой LLM -> (None, текст ошибки): вердикт тогда считается по прежним дорожкам."""
    try:
        llm_items, err = llm_rules(script, cache_path)
        if llm_items is None:
            return None, err
        by_id = {i["id"]: i for i in code_rules(script, open10_words) + llm_items}
        off = _disabled_ids()  # 22.10 профиль канала: правила чужой ниши не применяются
        return summarize([by_id[r["id"]] for r in RULES if r["id"] in by_id and r["id"] not in off]), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"[:200]


def _disabled_ids() -> set:
    """critic.rules_disabled в конфиге (профиль канала); без ключа пусто, поведение прежнее."""
    try:
        from .util import config
        v = (config().get("critic") or {}).get("rules_disabled") or []
    except Exception:
        v = []
    return {str(x) for x in v} if isinstance(v, list) else set()


def failed_items(rules) -> list[dict]:
    """Проваленные пункты (критичные первыми)."""
    if not isinstance(rules, dict):
        return []
    its = [i for i in rules.get("items") or [] if isinstance(i, dict) and not i.get("pass") and not i.get("na")]
    return sorted(its, key=lambda i: SEV_ORDER.get(i.get("severity"), 3))


def rules_notes(rules, limit: int = 8) -> str:
    """Проваленные правила и их fix -> текст для improve-заметок следующего авто-раунда (там же, где benchmark.borrow)."""
    fails = failed_items(rules)
    if not fails:
        return ""
    lines = [f"ПРАВИЛА СЦЕНАРИЯ (письменный стандарт владельца; выполнено {rules.get('passed')} из {rules.get('total')}). "
             "Исправь проваленные, критичные и важные в первую очередь; уже выполненное не ломай:"]
    for i in fails[:limit]:
        line = f"- [{SEV_LABEL.get(i['severity'], i['severity'])}] {i.get('title') or i['id']}: {i.get('fix') or i.get('definition', '')}"
        if i.get("kind") == "llm" and i.get("evidence"):
            line += f" (в тексте: {_quote(i['evidence'], 160)})"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":  # python -m pipeline.script_rules <job_id>: только правила кода, без LLM
    import sys
    from . import jobs
    jid = sys.argv[1]
    sc = json.loads((jobs.job_dir(jid) / "script.json").read_text(encoding="utf-8"))
    for it in code_rules(sc):
        print(("OK  " if it["pass"] else "FAIL"), it["id"], "|", it["evidence"], "|", it["fix"])
