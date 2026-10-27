#!/usr/bin/env python3
"""Замер скорости и качества TTS-голоса (для калибровки chars_per_minute).

Зачем: chars_per_minute в config/voices.yaml сейчас оценочный (vi=1000, выведен
из транскрипта брейкаута 6:31 ≈ 1500 слов). Этот скрипт даёт ТОЧНОЕ число на
реальном синтезе + mp3-файлы, чтобы на слух оценить «человечность» голоса.

Не требует API-ключей — использует Edge TTS (бесплатно, нужен только интернет).
Зависимости: pip install edge-tts ; ffprobe (входит в ffmpeg).

Запуск:
    python3 backend/tools/voice_probe.py
    python3 backend/tools/voice_probe.py --voices vi-VN-NamMinhNeural vi-VN-HoaiMyNeural
    python3 backend/tools/voice_probe.py --text-file my_sample.txt

Вывод: для каждого голоса — длительность, симв/мин, слов/мин и рекомендованное
значение chars_per_minute для voices.yaml. mp3 кладутся в backend/tools/out/.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Реалистичный сэмпл в тоне канала (hook + один блок доказательства).
# ~430 символов вьетнамского — достаточно для устойчивого замера темпа.
DEFAULT_SAMPLE = (
    "Bạn mở điện thoại lên chỉ để xem giờ, mười phút sau bạn vẫn đang lướt. "
    "Rồi tự nhiên bạn thấy chán. Và chính lúc đó tôi bắt đầu nghĩ tới một câu hỏi "
    "khá kỳ lạ: con người thời cổ đại đã làm gì khi họ chán? Không phải người La Mã, "
    "không phải Ai Cập cổ đại, mà là con người từ một trăm nghìn năm trước. "
    "Năm 1966, nhà nhân chủng học Marshall Sahlins công bố một nghiên cứu gây chấn động: "
    "người San ở Kalahari chỉ làm việc khoảng mười lăm đến hai mươi giờ mỗi tuần."
)

OUT_DIR = Path(__file__).parent / "out"


def _ffprobe_seconds(path: Path) -> float:
    """Длительность аудио в секундах через ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _synth_edge(text: str, voice: str, out_path: Path) -> None:
    """Синтез через edge-tts CLI (без ключей)."""
    subprocess.run(
        ["edge-tts", "--voice", voice, "--text", text,
         "--write-media", str(out_path)],
        capture_output=True, text=True, check=True,
    )


def probe(text: str, voices: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_chars = len(text)
    n_words = len(text.split())
    print(f"\nСэмпл: {n_chars} символов, {n_words} слов\n" + "─" * 60)

    for voice in voices:
        out_path = OUT_DIR / f"probe_{voice}.mp3"
        try:
            _synth_edge(text, voice, out_path)
            sec = _ffprobe_seconds(out_path)
        except FileNotFoundError as e:
            sys.exit(f"Нет инструмента: {e}. Нужно: pip install edge-tts + ffmpeg.")
        except subprocess.CalledProcessError as e:
            print(f"✗ {voice}: ошибка синтеза — {e.stderr[:200]}")
            continue

        cpm = n_chars / sec * 60
        wpm = n_words / sec * 60
        print(f"\n🎙  {voice}")
        print(f"   длительность : {sec:.1f} сек")
        print(f"   символов/мин : {cpm:.0f}   ← это значение в voices.yaml")
        print(f"   слов/мин     : {wpm:.0f}")
        print(f"   на 8 мин     : ~{cpm * 8:.0f} символов сценария")
        print(f"   mp3          : {out_path}")

    print("\n" + "─" * 60)
    print("Вставь символов/мин в config/voices.yaml → voices.vi.chars_per_minute")
    print("и в script.py chars_per_min (строки с {de,es,en,vi}). Послушай mp3 — "
          "если робот, бери ElevenLabs vi-голос (voice_id в voices.yaml).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Замер скорости TTS-голоса")
    ap.add_argument("--voices", nargs="+",
                    default=["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"],
                    help="Edge-голоса для сравнения")
    ap.add_argument("--text-file", type=Path,
                    help="Свой текст-сэмпл (по умолчанию — встроенный вьетнамский)")
    args = ap.parse_args()
    text = args.text_file.read_text(encoding="utf-8").strip() if args.text_file else DEFAULT_SAMPLE
    probe(text, args.voices)


if __name__ == "__main__":
    main()
