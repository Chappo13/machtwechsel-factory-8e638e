"""Валидатор/репейр данных Remotion-инфографики.

Контракт: каждое число / место / год / цитата в remotion_data должно быть НАЗВАНО
в тексте сцены (grounding). Что не подтверждается текстом — деградирует в сток, а
не рендерит уверенную ложь (как карта-«бублик» с угаданными координатами).

Чистые строковые операции, без LLM. magnitude НИКОГДА не блокирует подтверждённое
число (рост-хоккей и 50k-vs-3bn — суть жанра); grounding ловит только галлюцинации.

validate_remotion_data(scene) -> (visual_type, data_or_None, violations)
  visual_type: финальный тип ('remotion_*' | 'stock'); при деградации — 'stock', data=None.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

# ── числовой grounding ───────────────────────────────────────────────────────
_UNITS = {
    "milliarde": 1e9, "milliarden": 1e9, "mrd": 1e9, "bn": 1e9, "billion": 1e9,
    "million": 1e6, "millionen": 1e6, "mio": 1e6, "mln": 1e6,
    "tausend": 1e3, "tsd": 1e3,
}
_WORDS = {
    "null": 0, "ein": 1, "eine": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4,
    "funf": 5, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
    "elf": 11, "zwolf": 12, "zwölf": 12, "hundert": 100,
}
_UNIT_RE = "|".join(sorted(_UNITS, key=len, reverse=True))
_WORD_RE = "|".join(sorted(_WORDS, key=len, reverse=True))


def coerce_num(v):
    """LLM-значение → число или None ('1,9 Mrd' тоже)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v if v == v and abs(v) != float("inf") else None
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.,\-]", "", v).replace(",", ".")
        if cleaned.count(".") > 1:  # точки = разделители тысяч
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            n = float(cleaned)
            return int(n) if n.is_integer() else n
        except ValueError:
            return None
    return None


def _text_numbers(text: str) -> list[float]:
    """Все числа из текста, развёрнутые в базовые единицы."""
    t = (text or "").lower()
    out: list[float] = []
    # 1) <цифры> [unit]
    for m in re.finditer(r"(\d[\d.,]*)\s*(" + _UNIT_RE + r")?", t):
        raw, unit = m.group(1), m.group(2)
        n = coerce_num(raw)
        if n is None:
            continue
        out.append(n * _UNITS[unit] if unit else float(n))
    # 2) <слово-число> <unit>  (eine Milliarde, dreihundert Millionen, fünf Millionen)
    for m in re.finditer(r"(" + _WORD_RE + r")(hundert)?\s*(" + _UNIT_RE + r")", t):
        base = _WORDS.get(m.group(1), 0)
        if m.group(2):  # «dreihundert»
            base = base * 100 if base else 100
        out.append(base * _UNITS[m.group(3)])
    return out


def number_grounded(target, text: str, tol: float = 0.07) -> bool:
    """target подтверждается числом из текста в пределах ±tol (относительно)?"""
    tn = coerce_num(target)
    if tn is None:
        return False
    if tn == 0:
        return any(abs(x) < 1 for x in _text_numbers(text))
    return any(abs(x - tn) <= tol * abs(tn) for x in _text_numbers(text))


def _token_in_text(tok, text: str) -> bool:
    """Год/слово присутствует в тексте (по подстроке, нормализованно)."""
    s = re.sub(r"\s+", " ", str(tok)).strip().lower()
    return bool(s) and s in (text or "").lower()


# ── реестр иконок (для concept) ──────────────────────────────────────────────
_ICON_IDS: set[str] = set()


def _icon_ids() -> set[str]:
    global _ICON_IDS
    if _ICON_IDS:
        return _ICON_IDS
    try:
        p = Path(__file__).resolve().parents[1] / "config" / "concept_icons.json"
        _ICON_IDS = set(json.loads(p.read_text(encoding="utf-8")).get("icons", {}).keys())
    except Exception:
        _ICON_IDS = set()
    return _ICON_IDS


def _nonempty(s) -> bool:
    return bool(str(s or "").strip())


# ── главный валидатор ────────────────────────────────────────────────────────
def validate_remotion_data(scene: dict):
    """Возвращает (visual_type, data|None, violations). При деградации → ('stock', None, [...])."""
    vt = str(scene.get("visual_type") or "stock")
    text = str(scene.get("text") or "")
    data = scene.get("remotion_data")
    if not vt.startswith("remotion_"):
        return vt, None, []
    if not isinstance(data, dict):
        return "stock", None, [f"{vt}: нет remotion_data"]
    data = dict(data)  # копия
    v: list[str] = []

    def degrade(msg):
        v.append(msg)
        return "stock", None, v

    # accent — только hex
    a = str(data.get("accent", ""))
    if "accent" in data and not (a.startswith("#") and len(a) in (4, 7, 9)
                                 and all(c in "0123456789abcdefABCDEF" for c in a[1:])):
        data.pop("accent", None)

    if vt == "remotion_counter":
        to = coerce_num(data.get("to"))
        if to is None:
            return degrade("counter: нет числовой цели")
        if not number_grounded(to, text):
            return degrade(f"counter: {to} не в тексте сцены")
        data["to"] = to
        data["from"] = coerce_num(data.get("from")) or 0
        return vt, data, v

    if vt == "remotion_chart":
        pts = data.get("data")
        if not isinstance(pts, list):
            return degrade("chart: нет data")
        clean = []
        for p in pts:
            if not isinstance(p, dict):
                continue
            val = coerce_num(p.get("value"))
            if val is None or not _token_in_text(p.get("year"), text):
                continue
            clean.append({**p, "value": val})
        if len(clean) < 2:
            return degrade("chart: <2 точек с годом из текста")
        data["data"] = clean
        return vt, data, v

    if vt == "remotion_split":
        lv, rv = coerce_num(data.get("leftValue")), coerce_num(data.get("rightValue"))
        lc, rc = data.get("leftCountry"), data.get("rightCountry")
        ll, rl = data.get("leftLabel"), data.get("rightLabel")
        # numeric: оба числа и оба grounded → BarComparison
        if lv is not None and rv is not None and number_grounded(lv, text) and number_grounded(rv, text):
            left_label = ll or lc or ""
            right_label = rl or rc or ""
            if not (_nonempty(left_label) and _nonempty(right_label)):
                return degrade("split numeric: нет подписей")
            out = {"leftValue": lv, "leftLabel": str(left_label),
                   "rightValue": rv, "rightLabel": str(right_label),
                   "title": data.get("title", ""), "split_kind": "numeric"}
            if "accent" in data:
                out["accent"] = data["accent"]
            mx, mn = max(abs(lv), abs(rv)), min(abs(lv), abs(rv)) or 1
            if mx / mn > 100:
                out["ratio_badge"] = True
            return vt, out, v
        # textual: непустые строковые значения
        lvs, rvs = data.get("leftValue"), data.get("rightValue")
        if _nonempty(lvs) and _nonempty(rvs):
            out = {"leftCountry": str(lc or ll or ""), "leftValue": str(lvs),
                   "rightCountry": str(rc or rl or ""), "rightValue": str(rvs),
                   "leftSubtitle": data.get("leftSubtitle", ""),
                   "rightSubtitle": data.get("rightSubtitle", ""), "split_kind": "textual"}
            if not (_nonempty(out["leftCountry"]) and _nonempty(out["rightCountry"])):
                return degrade("split textual: нет подписей сторон")
            return vt, out, v
        return degrade("split: данные не подтверждены")

    if vt in ("remotion_map", "remotion_flow"):
        # места: из places (новый ключ) или старых pins (только имена)
        places = data.get("places")
        if not isinstance(places, list):
            pins = data.get("pins")
            places = [{"name": p.get("label")} for p in pins if isinstance(p, dict) and _nonempty(p.get("label"))] if isinstance(pins, list) else []
        names = [str(p.get("name")).strip() for p in places if isinstance(p, dict) and _nonempty(p.get("name"))]
        # поток A→B (новый формат) или ровно 2 места → FlowConnection
        fl, tl = data.get("fromLabel"), data.get("toLabel")
        if _nonempty(fl) and _nonempty(tl):
            out = {"fromLabel": str(fl), "toLabel": str(tl), "amount": str(data.get("amount", "")),
                   "fromSub": data.get("fromSub", ""), "toSub": data.get("toSub", ""),
                   "direction": data.get("direction", "oneway"), "title": data.get("title", "")}
            return "remotion_flow", out, v
        if len(names) == 2:
            out = {"fromLabel": names[0], "toLabel": names[1], "amount": str(data.get("amount", "")),
                   "direction": data.get("direction", "oneway"), "title": data.get("title", "")}
            return "remotion_flow", out, v
        return degrade("map/flow: нужен поток A→B или ровно 2 места")

    if vt == "remotion_concept":
        cap = data.get("caption")
        icon = str(data.get("icon", "")).strip()
        if not _nonempty(cap):
            return degrade("concept: нет подписи")
        if icon not in _icon_ids():
            return degrade(f"concept: иконка '{icon}' не в реестре")
        out = {"icon": icon, "caption": str(cap)}
        if "accent" in data:
            out["accent"] = data["accent"]
        return vt, out, v

    if vt == "remotion_stat":
        items = data.get("items")
        if not isinstance(items, list):
            return degrade("stat: нет items")
        clean = []
        for it in items[:4]:
            if not isinstance(it, dict):
                continue
            val = coerce_num(it.get("value"))
            if val is None or not number_grounded(val, text):
                continue
            clean.append({**it, "value": val})
        if not clean:
            return degrade("stat: нет подтверждённых чисел")
        data["items"] = clean
        return vt, data, v

    if vt == "remotion_timeline":
        evs = data.get("events")
        if not isinstance(evs, list):
            return degrade("timeline: нет events")
        clean = [e for e in evs if isinstance(e, dict) and _token_in_text(e.get("year"), text)]
        if len(clean) < 2:
            return degrade("timeline: <2 событий с годом из текста")
        data["events"] = clean
        return vt, data, v

    if vt == "remotion_ranked":
        items = data.get("items")
        if not isinstance(items, list):
            return degrade("ranked: нет items")
        clean = []
        for it in items:
            if not isinstance(it, dict):
                continue
            val = coerce_num(it.get("value"))
            if val is None or not _nonempty(it.get("label")) or not number_grounded(val, text):
                continue
            clean.append({**it, "value": val})
        if len(clean) < 2:
            return degrade("ranked: <2 подтверждённых пунктов")
        data["items"] = clean
        return vt, data, v

    if vt == "remotion_table":
        rows = data.get("rows")
        cols = data.get("columns")
        if not (isinstance(rows, list) and isinstance(cols, list) and len(cols) >= 2):
            return degrade("table: нет строк/колонок")
        clean = [r for r in rows if isinstance(r, dict) and (_nonempty(r.get("a")) or _nonempty(r.get("b")))]
        if not clean:
            return degrade("table: пустые строки")
        data["rows"] = clean
        return vt, data, v

    if vt in ("remotion_title", "remotion_quote"):
        key = "quote" if vt == "remotion_quote" else "title"
        if not _nonempty(data.get(key)):
            return degrade(f"{vt}: пустой {key}")
        return vt, data, v

    return vt, data, v
