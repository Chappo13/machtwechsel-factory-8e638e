"""
Text-to-Speech pipeline via Voicer API (ElevenLabs unlimited).

Features:
- Chunked synthesis (5000 chars per chunk)
- Language-specific preprocessing (abbreviations, numbers, pauses)
- Audio concatenation with natural pauses
- Duration detection via ffprobe
"""

import asyncio
import logging
import re
import subprocess
from pathlib import Path

import os
import shutil
import httpx

from backend.config import get_voice_config, VOICER_API_KEY

# Edge TTS (Microsoft, free, no API key). Install: pip install edge-tts
EDGE_DEFAULT_VOICES = {
    "de": os.getenv("EDGE_VOICE_DE", "de-DE-KatjaNeural"),
    "es": os.getenv("EDGE_VOICE_ES", "es-ES-ElviraNeural"),
    "en": os.getenv("EDGE_VOICE_EN", "en-US-AriaNeural"),
    "pl": os.getenv("EDGE_VOICE_PL", "pl-PL-ZofiaNeural"),
    "vi": os.getenv("EDGE_VOICE_VI", "vi-VN-NamMinhNeural"),
}

logger = logging.getLogger(__name__)


async def generate_voiceover(
    text: str,
    lang: str,
    output_dir: Path,
    progress_cb=None,
    tts_mode: str = "fal",
    voice_id_override: str = None,
) -> tuple[Path, float]:
    """
    Generate voiceover audio from script text.

    Args:
        text: Script text to synthesize
        lang: Language code (de, es, en)
        output_dir: Directory to save audio files
        voice_id_override: подменить voice_id поверх voices.yaml[lang] (мульти-язык:
            curiosity-голос целевого языка, минуя финанс-голос канала). Фонетика языка
            (language_code/settings) остаётся из voices.yaml[lang].

    Returns:
        Tuple of (audio_path, duration_seconds)
    """
    voice_config = get_voice_config(lang)
    if voice_id_override:
        voice_config = dict(voice_config)
        voice_config["voice_id"] = voice_id_override
        logger.info(f"TTS: voice_id_override → {voice_id_override} (lang={lang})")
    api_config = voice_config["api"]

    voice_id = voice_config.get("voice_id", "")
    if not voice_id:
        # Не валим прогон: пустой voice_id просто пропускает fal/Voicer,
        # диспетчер уходит на Edge TTS (edge_voice из voices.yaml).
        logger.warning(f"voice_id пуст для lang={lang} → Edge TTS fallback")

    # Preprocess text (разметка → чистый Sprechtext → языковые замены)
    processed = preprocess_text(clean_for_tts(text), lang)
    
    # Split into chunks
    chunk_size = voice_config.get("chunk_size", 5000)
    chunks = _split_into_chunks(processed, chunk_size)
    logger.info(f"TTS: {len(chunks)} chunks, {len(processed)} chars total")
    
    # Synthesize each chunk
    chunk_paths = []
    for i, chunk in enumerate(chunks):
        logger.info(f"TTS chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
        if progress_cb:
            try: progress_cb(f"Озвучка: фрагмент {i+1}/{len(chunks)}")
            except Exception: pass
        chunk_path = output_dir / f"tts_chunk_{i:03d}.mp3"

        # Ретраи: падение/пустой результат одного чанка не должно валить весь
        # ночной прогон. Диспетчер сам идёт fal→voicer→edge; здесь — устойчивость
        # к транзиентным сбоям сети/API.
        last_err = None
        for attempt in range(3):
            try:
                # Жёсткий таймаут: зависший TTS-запрос (видели висяк на «фрагмент 1/3»,
                # подвесивший весь контейнер) рвётся таймаутом → ретрай/чистая ошибка
                # вместо вечного freeze. 300с — ВЫШЕ fal read-timeout (240с): большой
                # чанк (~5к симв ≈ 5 мин аудио) легально синтезируется дольше 150с, а
                # 150с рвал его раньше fal → TimeoutError с пустым текстом → ложное падение.
                await asyncio.wait_for(
                    _synthesize_chunk_dispatch(
                        text=chunk,
                        lang=lang,
                        voice_config=voice_config,
                        api_config=api_config,
                        output_path=chunk_path,
                        tts_mode=tts_mode,
                    ),
                    timeout=300,
                )
                if chunk_path.exists() and chunk_path.stat().st_size > 1024:
                    break
                raise RuntimeError("пустой/слишком маленький файл чанка")
            except Exception as e:
                last_err = e
                logger.warning(f"TTS chunk {i+1} попытка {attempt+1}/3 не удалась: {e}")
                await asyncio.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"TTS chunk {i+1} не синтезирован после 3 попыток: {last_err}")
        chunk_paths.append(chunk_path)
    
    # Concatenate chunks with pauses
    final_path = output_dir / "voiceover.mp3"
    pause_duration = voice_config.get("pause_between_chunks", 0.4)
    _concatenate_audio(chunk_paths, final_path, pause_duration)
    
    # Get duration
    duration = _get_audio_duration(final_path)
    logger.info(f"TTS complete: {duration:.1f}s ({duration/60:.1f} min)")
    
    # Cleanup chunks
    for p in chunk_paths:
        p.unlink(missing_ok=True)
    
    return final_path, duration


def clean_for_tts(text: str) -> str:
    """Удаляет служебную разметку сценария перед синтезом.

    Диктор зачитывал вслух заголовки секций («**[HOOK: 0:00-0:15]**»),
    markdown-звёздочки и решётки. Сценарий хранится С разметкой (scene
    planning строит по ней главы), поэтому чистим только на входе в TTS.
    Regex, не LLM: формат плавает, а запрет в промпте доказанно не работает.
    """
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # строка-заголовок секции: **[TEIL 1 – ...: 3:00-8:00]**, [PAUSE] и т.п.
        if re.fullmatch(r"\*{0,2}\[[^\]]*\]\*{0,2}:?", stripped):
            continue
        # markdown-заголовки и горизонтальные линии
        if re.fullmatch(r"#{1,6}\s.*|[-=_*]{3,}", stripped):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    # остаточные inline-маркеры: **bold**, *italic*, __x__, `code`
    cleaned = re.sub(r"\*{1,2}([^*\n]+)\*{1,2}", r"\1", cleaned)
    cleaned = re.sub(r"_{2}([^_\n]+)_{2}", r"\1", cleaned)
    cleaned = cleaned.replace("`", "")
    # ИНЛАЙНОВЫЕ таймкод-заголовки, приклеенные к тексту на одной строке
    # («El hipotálamo. [El experimento: 5:30-7:40] Y entonces…») — построчный fullmatch
    # их пропускал, и диктор читал «cinco treinta a siete cuarenta». Узкий шаблон
    # (требует MM:SS внутри) не трогает обычные скобки без таймкода.
    cleaned = re.sub(r"\*{0,2}\[[^\]\n]*\d{1,2}:\d{2}[^\]\n]*\]\*{0,2}", "", cleaned)
    # схлопываем тройные+ пустые строки после вырезанных заголовков
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def preprocess_text(text: str, lang: str) -> str:
    """Preprocess text for TTS — expand abbreviations, fix special chars."""
    # Common replacements
    text = text.replace("&", " und " if lang == "de" else " y " if lang == "es" else " and ")
    text = text.replace("%", " Prozent" if lang == "de" else " por ciento" if lang == "es" else " percent")
    
    def _apply(replacements: dict) -> None:
        nonlocal text
        for old, new in replacements.items():
            # Аббревиатуры из одних букв/цифр (UE, PIB, CEO) заменяем ТОЛЬКО как
            # отдельное слово — иначе substring-replace рушит обычные слова
            # (UE→U.E. ломал CUERPO→CU.E.RPO, QUE→QU.E.). С точками (z.B., EE.UU.)
            # достаточно отличимы → обычная замена.
            if "." not in old and old.isalnum():
                text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
            else:
                text = text.replace(old, new)

    if lang == "de":
        _apply({
            "CEO": "C.E.O.",
            "CFO": "C.F.O.",
            "IPO": "I.P.O.",
            "USA": "U.S.A.",
            "EU": "E.U.",
            "z.B.": "zum Beispiel",
            "d.h.": "das heißt",
            "Mrd.": "Milliarden",
            "Mio.": "Millionen",
        })

    elif lang == "es":
        _apply({
            "CEO": "C.E.O.",
            "EE.UU.": "Estados Unidos",
            "UE": "U.E.",
            "PIB": "P.I.B.",
        })

    return text


def _split_into_chunks(text: str, max_size: int) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    sentences = []
    for para in text.split("\n"):
        for sent in para.replace(". ", ".\n").split("\n"):
            sent = sent.strip()
            if sent:
                sentences.append(sent)
    
    chunks = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 > max_size and current:
            chunks.append(current.strip())
            current = ""
        current += " " + sent
    if current.strip():
        chunks.append(current.strip())
    
    return chunks


# fal.ai → ElevenLabs v3 (sync endpoint; FALAPI). Основной путь, голоса как в voices.yaml.
FAL_TTS_URL = "https://fal.run/fal-ai/elevenlabs/tts/eleven-v3"
_FAL_LANG = {"de": "de", "es": "es", "en": "en", "pl": "pl", "ru": "ru", "vi": "vi"}


async def _synthesize_chunk_fal(text: str, lang: str, voice_config: dict, output_path: Path):
    """Озвучка чанка через fal.ai → ElevenLabs v3 (FALAPI)."""
    fal_key = os.getenv("FALAPI", "")
    headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}
    payload = {"text": text, "voice": voice_config.get("voice_id", "")}
    stab = (voice_config.get("settings") or {}).get("stability")
    if stab is not None:
        payload["stability"] = stab
    if _FAL_LANG.get(lang):
        payload["language_code"] = _FAL_LANG[lang]
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15, read=240, write=60, pool=240)) as client:
        resp = await client.post(FAL_TTS_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        audio = data.get("audio")
        url = audio.get("url") if isinstance(audio, dict) else (audio if isinstance(audio, str) else None)
        if not url:
            raise RuntimeError(f"fal TTS: нет audio url: {str(data)[:200]}")
        a = await client.get(url)
        a.raise_for_status()
        output_path.write_bytes(a.content)
    if not (output_path.exists() and output_path.stat().st_size > 5000):
        raise RuntimeError("fal TTS: пустой аудиофайл")


async def _synthesize_chunk_dispatch(
    text: str,
    lang: str,
    voice_config: dict,
    api_config: dict,
    output_path: Path,
    tts_mode: str = "fal",
):
    """Provider order: Voicer → fal→ElevenLabs v3 (FALAPI) → Edge.
    Voicer идёт первым когда ключ есть — клиент платит за 1М символов.
    Edge — ТОЛЬКО если платный голос не настроен вовсе (или ALLOW_EDGE_FALLBACK=1).
    tts_mode="free" — клиент ЯВНО выбрал бесплатную озвучку (Edge) для тестов.
    tts_mode="voicer" — форсировать Voicer (без fal-fallback)."""
    if tts_mode == "free":
        await _synthesize_chunk_edge(
            text=text, lang=lang, voice_config=voice_config, output_path=output_path)
        return

    # Voicer первым — оплаченный пакет 1М символов, рабочий провайдер
    if VOICER_API_KEY and voice_config.get("voice_id"):
        try:
            await _synthesize_chunk(
                text=text,
                voice_id=voice_config["voice_id"],
                model=voice_config["model"],
                settings=voice_config["settings"],
                api_config=api_config,
                output_path=output_path,
            )
            return
        except Exception as e:
            if tts_mode == "voicer":
                raise RuntimeError(f"Voicer TTS недоступен ({e}). Проверь баланс/ключ.")
            logger.warning(f"Voicer не сработал ({e}) → fal")

    # fal.ai → ElevenLabs v3 — резерв
    if os.getenv("FALAPI") and voice_config.get("voice_id") and tts_mode != "voicer":
        try:
            await _synthesize_chunk_fal(text, lang, voice_config, output_path)
            return
        except Exception as e:
            if os.getenv("ALLOW_EDGE_FALLBACK") == "1":
                logger.warning(f"fal TTS не сработал ({e}) → Edge (разрешён явно)")
                await _synthesize_chunk_edge(
                    text=text, lang=lang, voice_config=voice_config, output_path=output_path)
                return
            else:
                raise RuntimeError(
                    f"fal TTS недоступен ({e}). Подмена голоса на Edge отключена — "
                    f"проверь баланс на fal.ai/dashboard/billing и нажми «Продолжить»")

    # Fallback: Edge TTS (Microsoft, free, no API key)
    await _synthesize_chunk_edge(
        text=text, lang=lang, voice_config=voice_config, output_path=output_path,
    )


async def _synthesize_chunk_edge(
    text: str,
    lang: str,
    voice_config: dict,
    output_path: Path,
):
    """Synthesize a chunk via Edge TTS (Microsoft).

    Requires `edge-tts` package or CLI tool:
        pip install edge-tts

    Voice override priority:
        1. voice_config["edge_voice"]  (per-language YAML)
        2. env EDGE_VOICE_<LANG>
        3. EDGE_DEFAULT_VOICES[lang]
    """
    voice = voice_config.get("edge_voice") or EDGE_DEFAULT_VOICES.get(lang)
    if not voice:
        raise RuntimeError(f"No Edge TTS voice configured for lang={lang}")

    # Try Python package first (preferred — async-native)
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return
    except ImportError:
        pass  # fall through to CLI

    # Fallback: CLI tool
    cli = shutil.which("edge-tts")
    if not cli:
        raise RuntimeError(
            "Edge TTS not available. Install: pip install edge-tts"
        )
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        cli, "--voice", voice, "--text", text, "--write-media", str(output_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"edge-tts CLI failed: {stderr.decode()[:300]}")


async def _synthesize_chunk(
    text: str,
    voice_id: str,
    model: str,
    settings: dict,
    api_config: dict,
    output_path: Path,
):
    """Synthesize a single text chunk via Voicer API."""
    endpoint = api_config["endpoint"]
    auth_prefix = api_config.get("auth_prefix", "Bearer")
    
    headers = {
        api_config.get("auth_header", "Authorization"): f"{auth_prefix} {VOICER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model,
        "voice_settings": settings,
    }
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=60, write=30, pool=60)) as client:
        # Start synthesis
        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("task_id") or data.get("id")
        
        if not task_id:
            # Direct audio response (no async queue)
            content_type = resp.headers.get("content-type", "")
            if "audio" in content_type or "octet-stream" in content_type:
                output_path.write_bytes(resp.content)
                return
            else:
                raise RuntimeError(f"TTS returned unexpected response: {content_type}")
        
        # Poll for completion
        status_url = api_config["status_endpoint"].format(task_id=task_id)
        download_url = api_config["download_endpoint"].format(task_id=task_id)
        poll_interval = api_config.get("poll_interval", 2)
        max_polls = api_config.get("max_polls", 240)
        
        for _ in range(max_polls):
            await asyncio.sleep(poll_interval)
            status_resp = await client.get(status_url, headers=headers)
            status_data = status_resp.json()
            status = status_data.get("status", "")
            
            if status in ("completed", "done", "ready"):
                # Download audio
                audio_resp = await client.get(download_url, headers=headers)
                audio_resp.raise_for_status()
                output_path.write_bytes(audio_resp.content)
                return
            elif status in ("failed", "error"):
                raise RuntimeError(f"TTS failed: {status_data}")
        
        raise TimeoutError(f"TTS polling timeout after {max_polls * poll_interval}s")


def _concatenate_audio(chunk_paths: list[Path], output_path: Path, pause: float = 0.4):
    """Склейка аудио-чанков ВСТЫК с паузой тишины между ними.

    Раньше использовался amix=duration=longest + adelay — он МИКШИРУЕТ дорожки
    внахлёст, и на видео из >1 чанка голос накладывался сам на себя. Теперь
    каждый чанк нормализуется (провайдеры дают разный sample rate) и склеивается
    последовательно фильтром concat, с тишиной pause между чанками.
    """
    # ВЫХОД ВСЕГДА СТЕРЕО: моно-войсовер при audioChannels="2" в fcpxml DaVinci
    # кладёт в ОДИН (левый) канал — звук «только в левом ухе».
    if len(chunk_paths) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(chunk_paths[0]),
             "-ac", "2", "-ar", "44100", str(output_path)],
            capture_output=True, check=True, timeout=300)
        return

    inputs = []
    for path in chunk_paths:
        inputs.extend(["-i", str(path)])

    n = len(chunk_paths)
    parts = []
    for i in range(n):
        # нормализуем формат каждого чанка + добавляем паузу в конце (кроме последнего)
        pad = f",apad=pad_dur={pause}" if i < n - 1 else ""
        parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo{pad}[a{i}]")
    refs = "".join(f"[a{i}]" for i in range(n))
    filter_complex = ";".join(parts) + f";{refs}concat=n={n}:v=0:a=1[out]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ac", "2",
        "-ar", "44100",
        str(output_path),
    ]

    subprocess.run(cmd, capture_output=True, check=True, timeout=300)


def _get_audio_duration(path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
    return float(result.stdout.strip())
