"""Структурированное описание кадра (shot spec) и сборка из него промпта иллюстрации.

Owner 10.10: «картинки часто не совпадают с моментом» (80 рабочих тащат на санях
мраморного коня -> конь стоит отдельно, рабочие тянут не туда). Режиссёр заполняет
для каждого media-кадра поля (план, главный объект, действие с направлением, место,
эпоха/костюмы, свет, ракурс), а промпт собирает КОД в одном порядке и на английском,
плюс единый список запретов. Без свободного «опиши сцену».
"""
from __future__ import annotations

import re

SHOT_SIZES = ("extreme close-up", "close-up", "medium shot", "wide shot", "aerial view")
SPEC_FIELDS = ("shot_size", "subject", "action", "setting", "era_costume", "light_mood", "camera_angle")

NEGATIVE = ("no text, no letters, no captions, no watermark, no logo; "
            "no modern people, clothing or objects unless the narration names them; "
            "no extra limbs, no fused or duplicated people, no duplicated objects; "
            "no split panels or collage")

# Текстовые карточки: только если в озвучке есть ДАННЫЕ (числа/даты/размеры/сравнение).
TEXT_CARD_TYPES = frozenset({"board", "steps", "compare", "table", "quote", "diary", "fact_stack", "document"})

_NUM_WORDS = (r"один(?:надцат\w*)?|одн\w+|дв(?:а|е|ух|ум|умя)|двенадцат\w*|двадцат\w*|тр(?:и|ёх|ех|ем|емя)|"
              r"тринадцат\w*|тридцат\w*|четыр\w+|пят(?:ь|и|ью|надцат\w*)|шест(?:ь|и|ью|надцат\w*)|"
              r"сем(?:ь|и|ью|надцат\w*)|восем(?:ь|и|ью|надцат\w*)|девят\w+|\w*десят\w*|сорок\w*|девяност\w*|"
              r"сто|ста|сотн\w+|(?:пят|шест|сем|восем|девят)ьсот|двест\w+|тысяч\w*|миллион\w*|миллиард\w*|"
              r"полтор\w+|половин\w*|процент\w*|втор(?:ой|ого|ом)|трет(?:ий|ьего|ьем)")
_NUM_WORD_RE = re.compile(rf"(?<![\w])(?:{_NUM_WORDS})(?![\w])", re.I)


def data_tokens(text: str) -> int:
    """Сколько «данных» в озвучке: цифры/годы и числительные. 0 -> текстовой карточке тут не место."""
    t = (text or "").casefold().replace("ё", "е")
    return len(re.findall(r"\d+", t)) + len(_NUM_WORD_RE.findall(t))


def has_data(text: str) -> bool:
    return data_tokens(text) > 0


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().strip(".")


def normalize_spec(spec) -> dict:
    """Только известные поля, строки; пустое -> ''. Не dict -> {}."""
    if not isinstance(spec, dict):
        return {}
    return {k: _clean(spec.get(k)) for k in SPEC_FIELDS}


def spec_complete(spec: dict) -> bool:
    """Минимум для сборки промпта: главный объект и (действие ИЛИ место)."""
    s = normalize_spec(spec)
    return bool(s.get("subject")) and bool(s.get("action") or s.get("setting"))


def build_prompt(spec: dict, negative: bool = True) -> str | None:
    """Английский промпт строго в одном порядке: план, главный объект, действие, место,
    эпоха/костюмы, свет/настроение, ракурс, запреты. None, если spec неполный."""
    s = normalize_spec(spec)
    if not spec_complete(s):
        return None
    parts = []
    size = s["shot_size"]
    parts.append(f"{size[:1].upper()}{size[1:]}." if size else "")
    parts.append(f"Main subject: {s['subject']}.")
    if s["action"]:
        parts.append(f"Action and direction: {s['action']}.")
    if s["setting"]:
        parts.append(f"Setting and background: {s['setting']}.")
    if s["era_costume"]:
        parts.append(f"Era and costume: {s['era_costume']}.")
    if s["light_mood"]:
        parts.append(f"Light and mood: {s['light_mood']}.")
    if s["camera_angle"]:
        parts.append(f"Camera angle: {s['camera_angle']}.")
    if negative:
        parts.append(f"Avoid: {NEGATIVE}.")
    return " ".join(p for p in parts if p)


_MULTI_PERSON = re.compile(r"\b(workers|laborers|men|women|soldiers|crowd|people|sailors|villagers|team of|dozens?|"
                           r"hundreds?|\d{2,})\b", re.I)


def simplify_spec(spec: dict) -> dict:
    """Упрощённый вариант для ретрая: один главный объект, без сложного многолюдного
    действия, крупнее план. Нужен, когда сложная сцена не получилась/не прошла проверку."""
    s = normalize_spec(spec)
    subject = s["subject"]
    # если в «объекте» толпа — берём предмет из действия нельзя надёжно; оставляем как есть, но сокращаем
    if _MULTI_PERSON.search(subject):
        subject = "the key object of the scene, seen alone"
    setting = s["setting"].split(",")[0].strip() if s["setting"] else ""
    return {"shot_size": "close-up" if s["shot_size"] in ("", "wide shot", "aerial view", "medium shot") else s["shot_size"],
            "subject": subject, "action": "", "setting": setting or s["setting"],
            "era_costume": s["era_costume"], "light_mood": s["light_mood"],
            "camera_angle": "eye level" if not s["camera_angle"] else s["camera_angle"]}


def simplify_prompt_text(prompt_en: str) -> str:
    """Для старых планов без spec: первая фраза, короче, один объект, без людской толпы."""
    text = re.sub(r"\s+", " ", prompt_en or "").strip()
    first = re.split(r"(?<=[.;:])\s+", text, maxsplit=1)[0]
    first = re.split(r",\s*(?:while|as|with|and)\s", first, maxsplit=1)[0]
    first = first[:240].rstrip(" ,;:.")
    return f"Close-up, single main subject, simple composition: {first}. Avoid: {NEGATIVE}."


def prompt_for(data: dict) -> str | None:
    """Промпт иллюстрации для media.data: из shot_spec, иначе готовый illustration_prompt_en."""
    p = build_prompt(data.get("shot_spec"))
    if p:
        return p
    old = (data.get("illustration_prompt_en") or "").strip()
    return old or None
