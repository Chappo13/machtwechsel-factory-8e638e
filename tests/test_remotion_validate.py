"""Тесты валидатора Remotion-данных: grounding чисел/мест/лет в тексте сцены,
деградация в сток, ремап ключей split. Failure-first."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "remotion_validate",
    Path(__file__).resolve().parents[1] / "backend" / "pipeline" / "remotion_validate.py",
)
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)
V = rv.validate_remotion_data


def test_counter_grounded():
    vt, d, _ = V({"visual_type": "remotion_counter", "text": "142 Millionen Euro verschwanden",
                  "remotion_data": {"to": 142000000}})
    assert vt == "remotion_counter" and d["to"] == 142000000


def test_counter_ungrounded_degrades():
    vt, d, _ = V({"visual_type": "remotion_counter", "text": "Es ging um viel Geld",
                  "remotion_data": {"to": 999999}})
    assert vt == "stock" and d is None


def test_milliarde_grounding():
    vt, _, _ = V({"visual_type": "remotion_counter", "text": "fast 1,5 Milliarden Euro",
                  "remotion_data": {"to": 1500000000}})
    assert vt == "remotion_counter"


def test_german_word_number():
    vt, _, _ = V({"visual_type": "remotion_counter", "text": "rund dreihundert Millionen flossen ab",
                  "remotion_data": {"to": 300000000}})
    assert vt == "remotion_counter"


def test_map_two_pins_to_flow():
    vt, d, _ = V({"visual_type": "remotion_map", "text": "von Frankfurt nach Zypern",
                  "remotion_data": {"pins": [{"x": 1, "y": 2, "label": "Frankfurt"},
                                              {"x": 9, "y": 9, "label": "Zypern"}]}})
    assert vt == "remotion_flow" and d["fromLabel"] == "Frankfurt" and d["toLabel"] == "Zypern"


def test_split_numeric_remaps_to_bar_keys():
    vt, d, _ = V({"visual_type": "remotion_split", "text": "13 Prozent gegen 100 Prozent",
                  "remotion_data": {"leftValue": 13, "leftCountry": "Versprochen",
                                    "rightValue": 100, "rightCountry": "Real"}})
    assert vt == "remotion_split" and d["split_kind"] == "numeric" and "leftLabel" in d


def test_concept_bad_icon_degrades():
    vt, _, _ = V({"visual_type": "remotion_concept", "text": "...",
                  "remotion_data": {"icon": "zzz_unknown", "caption": "x"}})
    assert vt == "stock"


def test_stat_drops_ungrounded_tile():
    vt, d, _ = V({"visual_type": "remotion_stat", "text": "28 Festnahmen und 13 Prozent",
                  "remotion_data": {"items": [{"value": 28, "label": "a"}, {"value": 13, "label": "b"},
                                              {"value": 777, "label": "erfunden"}]}})
    assert vt == "remotion_stat" and len(d["items"]) == 2


def test_timeline_needs_grounded_years():
    vt, _, _ = V({"visual_type": "remotion_timeline", "text": "nur viel später",
                  "remotion_data": {"events": [{"year": 2009}, {"year": 2021}]}})
    assert vt == "stock"
