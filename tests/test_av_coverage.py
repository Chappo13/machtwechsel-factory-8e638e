"""
A/V coverage regression tests (pure-function, no external deps).

Покрывают баг «видеоряд кончается на половине голоса»:
  - alignment: канва = max(words[-1].end, реальная длина аудио) — короткий ответ
    Deepgram больше не схлопывает тайминги в первую половину.
  - spine: если суммарного медиа не хватает до конца голоса — последний клип
    дотягивается, чёрного хвоста нет.

Запуск:  python3 -m tests.test_av_coverage   (из корня проекта)

httpx/yaml не нужны для тестируемых функций — стабим их перед импортом.
"""
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Стаб тяжёлых зависимостей: модули импортируют их на уровне файла, но
# тестируемые функции (anchoring/spine) их не трогают.
for _mod in ("httpx",):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

from backend.pipeline.align_scenes import align_scenes_to_words  # noqa: E402
from backend.pipeline.fcpxml_export import _build_video_spine  # noqa: E402
import re as _re  # noqa: E402


def _words(tokens, total=960.0):
    """Ровный word-stream: N токенов на [0..total]."""
    step = total / len(tokens)
    return [{"word": t, "start": round(i * step, 3), "end": round((i + 1) * step, 3)}
            for i, t in enumerate(tokens)]


def _base_plan():
    # 3 сцены матчатся в word-stream, 3 хвостовые — НЕТ (уйдут в _fill_gaps).
    return [
        {"text": "the deutsche bank lost billions"},
        {"text": "young bankers dreamed of prestige"},
        {"text": "since the year two thousand"},
        {"text": "zzz qqq www alpha tail"},
        {"text": "yyy ppp mmm bravo tail"},
        {"text": "kkk lll nnn charlie tail"},
    ]


STREAM = ("the deutsche bank lost billions "
          "young bankers dreamed of prestige "
          "since the year two thousand").split()


def test_canvas_floor_extends_to_audio_duration():
    """Слова Deepgram кончаются на 960s, реальное аудио 1937s → план тянется до ~1937."""
    plan = _base_plan()
    words = _words(STREAM, total=960.0)
    align_scenes_to_words(plan, words, audio_duration=1937.0)
    last_end = plan[-1]["end"]
    assert last_end >= 1937.0 * 0.98, f"last scene end {last_end} < 1937 — канва схлопнулась"
    # монотонность и отсутствие наложений
    prev = 0.0
    for s in plan:
        assert s["start"] >= prev - 1e-6, f"наложение/обратный ход на {s}"
        assert s["end"] >= s["start"] - 1e-6
        prev = s["end"]


def test_without_floor_old_behavior_collapses():
    """Без audio_duration канва = words[-1].end=960 → хвост ~960 (демонстрирует баг)."""
    plan = _base_plan()
    words = _words(STREAM, total=960.0)
    align_scenes_to_words(plan, words)  # audio_duration=0.0
    last_end = plan[-1]["end"]
    assert last_end <= 970.0, f"ожидали схлопывание ~960, получили {last_end}"


def test_empty_words_uses_audio_duration():
    """Deepgram не дал слов → пропорционально по реальной длине аудио (полное покрытие)."""
    plan = _base_plan()
    align_scenes_to_words(plan, [], audio_duration=1937.0)
    last_end = plan[-1]["end"]
    assert last_end >= 1937.0 * 0.98, f"empty-words: хвост {last_end} < 1937"
    assert plan[0]["start"] == 0.0


def test_anchoring_survives_midblock_miss():
    """Блок несматченных сцен в середине (числа/аббревиатуры) не должен запирать
    окно — поздние сцены обязаны привязаться к реальной позиции в голосе."""
    matched = lambda p: f"{p}a {p}b {p}c {p}d {p}e"
    plan = [
        {"text": matched("s0")}, {"text": matched("s1")}, {"text": matched("s2")},
        {"text": "u3 " + "fill " * 104},   # 105 токенов, голова "u3" в потоке отсутствует
        {"text": "u4 " + "fill " * 104},
        {"text": "u5 " + "fill " * 104},
        {"text": matched("s6")}, {"text": matched("s7")}, {"text": matched("s8")},
    ]
    # word-stream: матч-сцены своими токенами, несматченные — "fill" (без u3/u4/u5)
    toks = []
    for p in ("s0", "s1", "s2"):
        toks += [f"{p}{c}" for c in "abcde"]
    toks += ["fill"] * 315  # 3 × 105 — реальная длина несматченных сцен
    for p in ("s6", "s7", "s8"):
        toks += [f"{p}{c}" for c in "abcde"]
    words = [{"word": t, "start": float(5 * i), "end": float(5 * (i + 1))} for i, t in enumerate(toks)]
    s6_word_idx = 15 + 315  # 330
    align_scenes_to_words(plan, words, audio_duration=float(5 * len(toks)))
    # сцена 6 должна стоять около реального времени слова (1650s), не интерполяция
    assert abs(plan[6]["start"] - 5 * s6_word_idx) <= 15.0, \
        f"scene6 start {plan[6]['start']} далеко от якоря {5*s6_word_idx} — окно заперлось"
    prev = 0.0
    for s in plan:
        assert s["start"] >= prev - 1e-6, "наложение таймингов"
        prev = s["end"]


def _spine_offsets(xml):
    """Парсит offset/duration (в кадрах) каждого asset-clip из spine XML."""
    out = []
    for m in _re.finditer(r'offset="(\d+)/3000s"[^>]*duration="(\d+)/3000s"', xml):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def test_spine_contiguous_no_gaps():
    """Клипы покрывают всю длину, медиа хватает → spine встык, без дыр/наложений, до конца."""
    voice = 1000.0
    clips = [{
        "asset_id": f"vr{10+k}", "name": f"clip_{k:03d}",
        "scene_start": float(k * 100), "media_dur": 120.0, "duration": 100.0,
    } for k in range(10)]
    xml, cursor = _build_video_spine(clips, voice)
    parts = _spine_offsets(xml)
    assert parts, "spine пуст"
    # встык: offset следующего == offset+duration предыдущего
    for (o1, d1), (o2, d2) in zip(parts, parts[1:]):
        assert o2 == o1 + d1, f"дыра/наложение: {o1}+{d1} != {o2}"
    # доходит до конца голоса (в пределах кадра)
    last_o, last_d = parts[-1]
    end_frames = last_o + last_d
    assert abs(end_frames - round(voice * 30) * 100) <= 100, f"конец spine {end_frames} != голос"
    assert cursor >= voice - 0.5, f"cursor {cursor} не дошёл до {voice}"


def test_spine_frame_contiguous_fractional():
    """Дробные (не кратные кадру) тайминги → offset(N+1) обязан быть РОВНО offset(N)+dur(N)
    в кадрах. Старый код округлял offset и duration независимо → ±1 кадр щель (чёрная вспышка)."""
    voice = 300.0
    # неровные стартовые позиции (типичные тайминги сцен), шаг ~6.337с
    clips = [{
        "asset_id": f"vr{10+k}", "name": f"clip_{k:03d}",
        "scene_start": round(k * 6.337, 3), "media_dur": 30.0, "duration": 6.337,
    } for k in range(40)]
    xml, _ = _build_video_spine(clips, voice)
    parts = _spine_offsets(xml)
    assert len(parts) >= 30, f"мало клипов: {len(parts)}"
    bad = [(k, parts[k], parts[k+1]) for k in range(len(parts)-1)
           if parts[k+1][0] != parts[k][0] + parts[k][1]]
    assert not bad, f"щели/наложения на стыках (кадры): {bad[:5]}"


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
