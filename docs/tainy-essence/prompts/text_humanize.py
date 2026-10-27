"""Нормализация текста перед TTS: числа/годы/проценты словами, упрощение технических
кодов. Чистые функции без внешних зависимостей.

Портировано и адаптировано из старого проекта
(/home/agent/archive/projects/youtube-longs/scripts/text_humanizer.py) — см.
OLD-PROJECT-HARVEST.md §2.7. Используется в pipeline/tts.py перед отправкой текста
в Gemini TTS / edge-tts (и Gemini, и edge хуже читают голые цифры/коды).

Юнит-тесты: `python -m pipeline.text_humanize` (без pytest — его нет в venv).
"""
from __future__ import annotations

import re

# ---------- числа в слова (русский) ----------

UNITS = {
    0: "", 1: "один", 2: "два", 3: "три", 4: "четыре",
    5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
    10: "десять", 11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
    14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать",
    17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать",
}
TENS = {
    2: "двадцать", 3: "тридцать", 4: "сорок", 5: "пятьдесят",
    6: "шестьдесят", 7: "семьдесят", 8: "восемьдесят", 9: "девяносто",
}
HUNDREDS = {
    1: "сто", 2: "двести", 3: "триста", 4: "четыреста",
    5: "пятьсот", 6: "шестьсот", 7: "семьсот", 8: "восемьсот", 9: "девятьсот",
}
UNITS_FEMININE = {1: "одна", 2: "две"}

ORDINALS_NOM = {
    0: "", 1: "первый", 2: "второй", 3: "третий", 4: "четвёртый",
    5: "пятый", 6: "шестой", 7: "седьмой", 8: "восьмой", 9: "девятый",
    10: "десятый", 11: "одиннадцатый", 12: "двенадцатый",
    13: "тринадцатый", 14: "четырнадцатый", 15: "пятнадцатый",
    16: "шестнадцатый", 17: "семнадцатый", 18: "восемнадцатый",
    19: "девятнадцатый", 20: "двадцатый",
}
ORDINALS_PREP = {
    0: "", 1: "первом", 2: "втором", 3: "третьем", 4: "четвёртом",
    5: "пятом", 6: "шестом", 7: "седьмом", 8: "восьмом", 9: "девятом",
    10: "десятом", 11: "одиннадцатом", 12: "двенадцатом",
    13: "тринадцатом", 14: "четырнадцатом", 15: "пятнадцатом",
    16: "шестнадцатом", 17: "семнадцатом", 18: "восемнадцатом",
    19: "девятнадцатом", 20: "двадцатом",
}


def _under_1000(n: int, feminine: bool = False) -> str:
    if n == 0:
        return ""
    parts = []
    if n >= 100:
        parts.append(HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        parts.append(TENS[n // 10])
        n %= 10
    if 0 < n < 20:
        parts.append(UNITS_FEMININE[n] if feminine and n in UNITS_FEMININE else UNITS[n])
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """Число -> слова (русский), до ~999 999 999."""
    if n == 0:
        return "ноль"
    if n < 0:
        return "минус " + number_to_words(-n)

    parts = []
    if n >= 1_000_000:
        millions = n // 1_000_000
        n %= 1_000_000
        mw = _under_1000(millions)
        if millions % 10 == 1 and millions % 100 != 11:
            parts.append(f"{mw} миллион")
        elif millions % 10 in (2, 3, 4) and millions % 100 not in (12, 13, 14):
            parts.append(f"{mw} миллиона")
        else:
            parts.append(f"{mw} миллионов")
    if n >= 1000:
        thousands = n // 1000
        n %= 1000
        tw = _under_1000(thousands, feminine=True)
        if thousands % 10 == 1 and thousands % 100 != 11:
            parts.append(f"{tw} тысяча")
        elif thousands % 10 in (2, 3, 4) and thousands % 100 not in (12, 13, 14):
            parts.append(f"{tw} тысячи")
        else:
            parts.append(f"{tw} тысяч")
    if n > 0:
        parts.append(_under_1000(n))
    return " ".join(p for p in parts if p)


def year_to_words(year: int, case: str = "nominative") -> str:
    """Год -> слова с порядковым числительным в конце ('в XXXX году')."""
    if year < 1000 or year > 2100:
        return str(year)
    thousands, remainder = divmod(year, 1000)
    parts = []
    if thousands == 1:
        parts.append("тысяча")
    elif thousands == 2:
        parts.append("две тысячи")
    else:
        parts.append(number_to_words(thousands) + " тысяч")

    if remainder >= 100:
        parts.append(HUNDREDS[remainder // 100])
        remainder %= 100
    if remainder >= 20:
        parts.append(TENS[remainder // 10])
        remainder %= 10

    ordinals = ORDINALS_PREP if case == "prepositional" else ORDINALS_NOM
    if remainder in ordinals and ordinals[remainder]:
        parts.append(ordinals[remainder])
    elif remainder > 0:
        parts.append(ordinals.get(remainder % 10, str(remainder)))
    return " ".join(p for p in parts if p)


# ---------- технические коды ----------

TECHNICAL_PATTERNS: list[tuple[str, str]] = [
    # Астероидные/каталожные коды: "99942 Апофис" -> "Апофис"
    (r"\b(\d{4,6})\s+([А-ЯЁA-Z][а-яёa-z]+)", r"\2"),
    # Коды в скобках: "(2004 MN4)" -> ""
    (r"\s*\(\d{4}\s*[A-Z]{1,3}\d*\)", ""),
    (r"ГОСТ\s*[\d.\-]+", ""),
    (r"\s*\(ISO\s*[\d\-]+\)", ""),
    (r"NGC\s*\d+", "объект"),
    (r"\s*\(\d+\.\d+,\s*\d+\.\d+\)", ""),
]


def simplify_technical_codes(text: str) -> str:
    result = text
    for pattern, repl in TECHNICAL_PATTERNS:
        result = re.sub(pattern, repl, result)
    return re.sub(r"\s{2,}", " ", result)


# ---------- числа -> слова в контексте ----------

_UNIT_WORD_RE = (
    r"метр(?:ов|а)?|километр(?:ов|а)?|миллион(?:ов|а)?|тысяч[иа]?|"
    r"лет|года?|дней|часов?|минут(?:ы)?"
)


def humanize_numbers_for_tts(text: str) -> str:
    result = text

    # нормализация чисел с пробелами-разрядами (31 000 -> 31000)
    for _ in range(3):
        result = re.sub(r"(\d)\s+(\d{3})(?=\s|\D|$)", r"\1\2", result)

    def repl_year_prep(m: re.Match) -> str:
        year = int(m.group(1))
        if 1000 <= year <= 2100:
            return f"в {year_to_words(year, 'prepositional')} году"
        return m.group(0)

    result = re.sub(r"в\s+(\d{4})\s+году", repl_year_prep, result, flags=re.IGNORECASE)

    def repl_year_nom(m: re.Match) -> str:
        year = int(m.group(1))
        if 1000 <= year <= 2100:
            return f"{year_to_words(year, 'nominative')} год"
        return m.group(0)

    result = re.sub(r"(\d{4})\s+год(?![ауе])", repl_year_nom, result)

    def repl_num_unit(m: re.Match) -> str:
        num = int(m.group(1))
        unit = m.group(2)
        if num > 100000:
            return m.group(0)
        return f"{number_to_words(num)} {unit}"

    result = re.sub(rf"(\d+)\s*({_UNIT_WORD_RE})", repl_num_unit, result, flags=re.IGNORECASE)

    def repl_percent(m: re.Match) -> str:
        raw = m.group(1)
        if "." in raw or "," in raw:
            raw = raw.replace(",", ".")
            int_part, _, dec_part = raw.partition(".")
            int_words = number_to_words(int(int_part)) if int_part else "ноль"
            if dec_part:
                dec_words = number_to_words(int(dec_part))
                fraction = {1: "десятых", 2: "сотых"}.get(len(dec_part), "тысячных")
                return f"{int_words} целых {dec_words} {fraction} процента"
            return f"{int_words} процентов"
        num = int(raw)
        if num > 100:
            return m.group(0)
        words = number_to_words(num)
        if num % 10 == 1 and num % 100 != 11:
            suffix = "процент"
        elif num % 10 in (2, 3, 4) and num % 100 not in (12, 13, 14):
            suffix = "процента"
        else:
            suffix = "процентов"
        return f"{words} {suffix}"

    result = re.sub(r"(\d+[.,]?\d*)%", repl_percent, result)
    return result


def humanize_text(text: str, convert_numbers: bool = True, simplify_codes: bool = True) -> str:
    """Полная обработка текста перед TTS."""
    result = text
    if simplify_codes:
        result = simplify_technical_codes(result)
    if convert_numbers:
        result = humanize_numbers_for_tts(result)
    return result


def _run_tests() -> None:
    assert number_to_words(0) == "ноль"
    assert number_to_words(7) == "семь"
    assert number_to_words(130) == "сто тридцать"
    assert number_to_words(2560) == "две тысячи пятьсот шестьдесят"
    assert number_to_words(12000) == "двенадцать тысяч"
    assert number_to_words(1) == "один"
    assert number_to_words(21) == "двадцать один"

    assert year_to_words(2029, "prepositional") == "две тысячи двадцать девятом"
    assert year_to_words(1958, "nominative") == "тысяча девятьсот пятьдесят восьмой"
    assert year_to_words(1800, "nominative") == "тысяча восемьсот"

    assert simplify_technical_codes("99942 Апофис пролетит мимо") == "Апофис пролетит мимо"
    assert "(2004 MN4)" not in simplify_technical_codes("Апофис (2004 MN4) известен")
    assert simplify_technical_codes("Стандарт ГОСТ 12345-67 устарел") == "Стандарт устарел"

    out = humanize_numbers_for_tts("Это случилось в 2029 году.")
    assert "две тысячи двадцать девятом году" in out, out

    out = humanize_numbers_for_tts("Высота достигает 146 метров.")
    assert "сто сорок шесть метров" in out, out

    out = humanize_numbers_for_tts("Уровень вырос на 15%.")
    assert "пятнадцать процентов" in out, out

    out = humanize_numbers_for_tts("Погрешность составила 2.7%.")
    assert "два целых семь десятых процента" in out, out

    out = humanize_numbers_for_tts("Возраст находки — 31 000 лет.")
    assert "тридцать одна тысяча лет" in out, out

    full = humanize_text("В 1958 году музей купил 99942 Апофис за 15% бюджета.")
    assert "тысяча девятьсот пятьдесят восьмом году" in full
    assert "99942" not in full
    assert "пятнадцать процентов" in full

    print("text_humanize: all tests passed")


if __name__ == "__main__":
    _run_tests()
