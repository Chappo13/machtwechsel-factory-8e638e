"""
Stick-figure visual mode.

Заменяет clip_download для visual_mode="stick_figure".

КЛЮЧЕВОЕ: переиспользует тайминг-логику download_clips (clips.py), а не дублирует:
  - _merge_short_scenes  → лекарство от мельтешения (сцены < 3.5с сливаются)
  - split_scenes         → длинные сцены → ~6с шоты (визуальное разнообразие)
  - slot_sec по формуле download_clips (перекрытие до старта следующего шота)
  - reuse-fallback       → упавшая генерация НЕ создаёт дыру (берём прошлый клип)
  - _render_infographic  → data-сцены (счётчики/графики/карты) рендерятся как
                           Remotion с РЕАЛЬНЫМИ числами, а не дудлом без данных

Инвариант: каждый шот получает клип ровно на свой slot_sec → сумма = таймлайну
голоса, рассинхрона нет.

Цена: ~50-70 картинок на 7-8-мин видео × $0.03 (Seedream v4) ≈ $1.5-2.1.
Модель/endpoint/params — в config/models.yaml → image_generation (swappable).
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path
from typing import Optional

import httpx

from backend.config import get_model_config, get_image_config, DATA_DIR
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)

# Арт-стиль референсных каналов (Góc Nhìn Khác / explainer-cartoon): простой
# круглоголовый персонаж, но ВСЕГДА внутри детально обставленной сцены с фоновыми
# предметами, тёплым светом и глубиной. НЕ один объект на белом — это была старая
# ошибка (клиент: «картинки бедные, один объект, не насыщено»).
STYLE_PREFIX = (
    "flat-color 2D cartoon illustration in a warm cozy explainer-video style, "
    "a simple round-headed character with thin clean outlines, placed inside a "
    "FULLY DETAILED environment rich with background props, furniture and depth, "
    "soft warm cinematic lighting, gentle shadows, muted storybook color palette, "
    "a complete scene that fills the whole 16:9 frame, no empty or blank background; "
    "absolutely NO text, NO words, NO letters, NO captions, NO numbers, NO signs, NO "
    "labels and NO watermarks anywhere in the image — a purely visual wordless illustration"
)

# Версия арт-стиля. При смене STYLE_PREFIX/промптов — БАМПНИ: тогда следующий build
# один раз перегенерит картинки в новом стиле, а дальнейшие пересборки той же версии
# переиспользуют PNG (бесплатно). См. инвалидацию кэша в generate_stick_images_*.
STYLE_VERSION = "v2-rich-scene"

# Стиль авто-превью (обложки): крупное эмоциональное лицо + место под заголовок.
# Тот же тёплый мультяшный стиль, но кадр-обложка, не сцена. Текст Seedream рендерит
# чисто (проверено клиентом на «TU CUERPO TE DELATA»).
THUMB_STYLE = (
    "a bold, clickable YouTube thumbnail, 16:9, in a SIMPLE hand-drawn stick-figure doodle "
    "style (white round-headed characters with thin black-outline stick limbs, xkcd-like, "
    "minimal but very expressive); ONE clear, instantly-readable SCENE that shows the "
    "emotional heart of the topic with 1-3 stick figures (strong, exaggerated facial "
    "emotion) plus one or two simple props or a contrasting element that hints at the stakes "
    "— NOT an abstract pattern, NOT a tiny detail, NOT an extreme close-up; flat saturated "
    "background, mood set by color (bright warm colors for cozy/positive topics, dark moody "
    "browns/blues for danger or tension); high contrast, big and clear on a small phone "
    "screen; leave the TOP strip cleaner for a large caption"
)

# Дефолт — Seedream v4 (чистый мульт), СИНХРОННЫЙ endpoint (~5-8с, без очереди).
# Переопределяется models.yaml → image_generation.endpoint.
FAL_QUEUE_URL = "https://fal.run/fal-ai/bytedance/seedream/v4/text-to-image"
DEFAULT_IMG_PARAMS = {"image_size": "landscape_16_9", "num_images": 1, "enable_safety_checker": False}

# ── image-to-image: референс-персонаж (Mack-стиль) для консистентности ─────────
# Если файл assets/char_ref.png есть — КАЖДАЯ генерация идёт через Seedream v4 edit
# с этим референсом: персонаж и рисовка одинаковые во всех сценах (как у AxenCool/
# Mack). Файла нет → fallback на text-to-image. Цена та же (~$0.03/картинка).
FAL_EDIT_URL = "https://fal.run/fal-ai/bytedance/seedream/v4/edit"
# Референс приоритет: загруженный клиентом на сайте (том, переживает деплой) >
# дефолт зашитый в образ. Менять референс = загрузить новый на сайте, без передеплоя.
REF_OVERRIDE_PATH = DATA_DIR / "reference" / "char_ref.png"  # том
CHAR_REF_PATH = Path(__file__).parent.parent / "assets" / "char_ref.png"  # дефолт в образе
_CHAR_REF_CACHE = None  # data URI, или "" если файла нет
_CHAR_REF_SIG = None    # (path, mtime_ns) под кэшем — новая загрузка меняет → перечитываем

# i2i-промпт РАЗДЕЛЯЕТ стиль и сцену. Без этого «Keep the EXACT same…» заставляет
# Seedream копировать композицию/панели листа-референса. Шаблон откалиброван вручную
# на проде (река/закат/пещера вышли цельными сценами, без сетки).
_EDIT_STYLE_GUIDE = (
    "Use the reference image ONLY for: character design, facial expression style, "
    "line quality, color palette, prehistoric environment design. "
    "Do NOT copy composition. Do NOT copy poses. Do NOT copy camera angle. "
    "Do NOT recreate any panel from the reference image. "
    "Create a completely new illustration in the same cartoon universe. "
    "Use the same visual style and character design as the reference image.\n"
    "STYLE: Hand-drawn thick black-outline cartoon. Simple prehistoric educational "
    "cartoon. Flat solid colors. Minimal shading. Expressive round-headed characters. "
    "Clean readable shapes. Warm cozy color palette. Rich detailed background. Not realistic."
)
_EDIT_SCENE_CLOSER = (
    "Single full-frame illustration. No split panels. No storyboard. No collage. "
    "No comic strip. No grid. Single cinematic illustration. One coherent scene."
)
_EDIT_NO_TEXT = "No text. No letters. No words anywhere in the image."


def _active_ref_path() -> Optional[Path]:
    """Активный референс: загруженный клиентом важнее дефолтного."""
    for p in (REF_OVERRIDE_PATH, CHAR_REF_PATH):
        try:
            if p.exists() and p.stat().st_size > 1000:
                return p
        except OSError:
            continue
    return None


def _ref_mime(b: bytes) -> str:
    if b[:8].startswith(b"\x89PNG"):
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _char_ref_datauri() -> str:
    """База64 data URI референс-персонажа для i2i. Кэш инвалидируется по mtime →
    загрузил новую картинку на сайте = подхватится в следующей сборке без передеплоя.
    Пусто → нет референса → text-to-image."""
    global _CHAR_REF_CACHE, _CHAR_REF_SIG
    p = _active_ref_path()
    if p is None:
        _CHAR_REF_CACHE, _CHAR_REF_SIG = "", None
        return ""
    try:
        sig = (str(p), p.stat().st_mtime_ns)
        if sig != _CHAR_REF_SIG:
            import base64
            data = p.read_bytes()
            _CHAR_REF_CACHE = (f"data:{_ref_mime(data)};base64,"
                               + base64.b64encode(data).decode())
            _CHAR_REF_SIG = sig
            logger.info(f"i2i: референс-персонаж загружен ({p})")
    except Exception as e:
        logger.warning(f"i2i: референс не загружен ({e}) — text-to-image")
        _CHAR_REF_CACHE, _CHAR_REF_SIG = "", None
    return _CHAR_REF_CACHE

SLOT_CAP_SEC = 25.0  # страховка от битых таймингов alignment (как в download_clips)


# ── Генерация промптов из текста сцены ────────────────────────────────────────

def _strip_markdown(s: str) -> str:
    """Снять markdown-разметку, которой Gemini оборачивает строки списка."""
    s = s.strip()
    s = re.sub(r"^[\s>*#\-\d.)\]]+", "", s)  # ведущие маркеры списка/цитат/чисел
    s = s.replace("**", "").replace("*", "").replace("`", "")
    return s.strip()


async def _generate_prompts_batch(
    items: list[dict], topic: str, prev_prompts: list[str] | None = None
) -> list[str]:
    """Промпт на каждый шот. items: [{narration, intended, k, n}].

    Главный урок с прода: Flux Schnell хорошо рисует КОНКРЕТНЫЕ простые предметы
    (конверт, лупа, машина, колба, часы) и человечка с ясной позой, но на
    АБСТРАКЦИЯХ/метафорах («visualization of code», «pressure cooker metaphor»,
    «entangled system symbolizing corruption») выдаёт чёрные каракули. Поэтому
    промпт обязан быть конкретным узнаваемым объектом/действием. Учитывает
    вариативность кусков одной сцены (k/n) и хвост прошлого батча (prev_prompts)."""
    model_cfg = get_model_config("scene_tagging")

    lines = []
    for i, it in enumerate(items):
        tag = ""
        if it.get("n", 1) > 1:
            tag = f" (image {it['k']}/{it['n']} of this beat — show a DIFFERENT moment/angle/place than the others)"
        narr = (it.get("narration") or "")[:220]
        lines.append(f"Scene {i + 1}{tag}: {narr}")
    scenes_text = "\n".join(lines)

    avoid_block = ""
    if prev_prompts:
        recent = "\n".join(f"- {p}" for p in prev_prompts[-8:] if p)
        if recent:
            avoid_block = (
                "\nAlready drawn in the previous shots — make the next ones clearly "
                f"different (new object/pose/framing):\n{recent}\n"
            )

    response = await call_llm(
        prompt=f"""You are the storyboard artist for a warm, detailed flat-cartoon explainer video about "{topic}".
For each scene's narration, describe ONE fully-composed CARTOON SCENE in this fixed style: "{STYLE_PREFIX}".

Each image is a complete little scene — a simple round-headed character DOING something inside a
SPECIFIC, richly detailed PLACE, not a lone icon floating on a blank background. Think the
explainer-cartoon look (Cyanide & Happiness / Góc Nhìn Khác): the character stays simple, but the
WORLD around them is full of props, furniture, depth and warm light.

HARD RULES:
1. ALWAYS A SETTING. Name a concrete place and fill it with background detail. Examples:
   - studying → "a cozy classroom: chalkboard covered in equations, rows of wooden desks, a globe, warm afternoon light through tall windows"
   - money stress → "a cluttered kitchen counter buried in paper receipts, a phone showing a banking app, cabinets behind"
   - long journey → "a winding dirt road through green hills at sunset, a small backpacker walking, distant mountains"
2. THE CHARACTER ACTS. Give one clear pose/emotion that matches the narration (sitting head-in-hands, counting coins, reading by lamplight, pointing, walking, looking worried) INSIDE that place.
3. CONCRETE, NEVER ABSTRACT. Translate any abstract idea into a physical everyday scene. BANNED as the subject: abstract, concept, symbolizing, representing, metaphor, visualization, "sense of", "idea of".
4. RICH BUT GROUNDED: name 3-6 specific background props that anchor the scene, plus the lighting/mood (warm, cozy, golden hour, dim evening, etc.).
5. Background text is fine only as texture (a chalkboard, a sign, scattered receipts) — never a big readable headline or logo as the point of the image.
6. Each scene visibly DIFFERENT from its neighbours — change the place, the action, or the camera framing. For "image k/n of this beat", pick a different moment/angle of the same situation.
7. 12-30 words, English only, no markdown. Format EXACTLY: "Scene N: description".
{avoid_block}
Scenes (narration to illustrate):
{scenes_text}

Return ONLY the scene lines, nothing else.""",
        model=model_cfg["primary"],
        temperature=0.8,
        max_tokens=50 * len(items),
    )

    prompts = [""] * len(items)
    for raw_line in (response or "").strip().split("\n"):
        line = _strip_markdown(raw_line)
        m = re.match(r"Scene\s+(\d+)\s*[:\-]\s*(.+)", line, re.IGNORECASE)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(items):
                prompts[idx] = m.group(2).strip()

    for j, p in enumerate(prompts):
        if not p:
            prompts[j] = ("a round-headed cartoon character sitting at a wooden desk in a cozy "
                          "room, books, a lamp and a window with warm evening light behind")

    return prompts


async def _verify_prompts_batch(prompts: list[str], topic: str) -> list[str]:
    """Проверка промптов (то, что просил клиент): второй LLM-проход ревизует все
    промпты вместе и ЧИНИТ проблемные — сросшиеся фигура+объект, слишком детальные,
    повторяющие соседа, расплывчатые. Хорошие оставляет как есть."""
    model_cfg = get_model_config("scene_tagging")
    listing = "\n".join(f"Prompt {i + 1}: {p}" for i, p in enumerate(prompts))

    response = await call_llm(
        prompt=f"""These are scene descriptions for a warm, detailed flat-cartoon video about "{topic}", in sequence.
They will be drawn as full little cartoon scenes — a simple character inside a richly detailed setting.
Output A FINAL version of every prompt. Fix a prompt ONLY if it breaks a rule; else repeat unchanged.

Rules:
1. ALWAYS A SETTING with 3-6 background props (a real place, furniture, atmosphere, lighting) — never a single object or character floating on a blank/white background. If a prompt is just one bare icon → put it INTO a concrete scene with the character.
2. CONCRETE, NEVER ABSTRACT. If abstract (abstract, concept, symbolizing, metaphor, visualization, "sense/idea of") → rewrite as a physical everyday scene (e.g. "pressure at work" → "a character slumped at a paper-covered desk under a dim office lamp").
3. The character has a clear action/emotion that fits the narration.
4. Background text is fine as texture, but no big readable headline or logo as the subject.
5. Each must DIFFER from its neighbours (place / action / framing). If two adjacent are near-duplicates → change the place or angle of one.
6. 12-30 words.

Output EXACTLY one line per prompt, same count and order: "Prompt N: final description". No markdown.

{listing}""",
        model=model_cfg["primary"],
        temperature=0.5,
        max_tokens=50 * len(prompts) + 200,
    )

    fixed = list(prompts)
    for raw in (response or "").strip().split("\n"):
        line = _strip_markdown(raw)
        m = re.match(r"Prompt\s+(\d+)\s*[:\-]\s*(.+)", line, re.IGNORECASE)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(fixed) and m.group(2).strip():
                fixed[idx] = m.group(2).strip()
    return fixed


def _build_items(stick_shots: list[dict]) -> list[dict]:
    """Группирует подряд идущие шоты одной сцены (одинаковый text+on_screen) и
    проставляет вариативный индекс k/n — чтобы N кусков длинной сцены получили N
    РАЗНЫХ конкретных объектов, а не одно и то же on_screen N раз."""
    items: list[dict] = []
    i, n_shots = 0, len(stick_shots)
    while i < n_shots:
        key = (stick_shots[i].get("text"), stick_shots[i].get("on_screen"))
        j = i
        while j < n_shots and (stick_shots[j].get("text"), stick_shots[j].get("on_screen")) == key:
            j += 1
        group = stick_shots[i:j]
        for k, s in enumerate(group, 1):
            items.append({
                "narration": s.get("text") or s.get("on_screen") or "",
                "intended": s.get("on_screen") or "",
                "k": k, "n": len(group),
            })
        i = j
    return items


async def _generate_all_prompts(stick_shots: list[dict], topic: str, progress_cb=None) -> list[str]:
    # Меньший батч (18) + память хвоста прошлого батча = лучше variety на стыках
    items = _build_items(stick_shots)
    BATCH = 18
    all_prompts: list[str] = []
    for i in range(0, len(items), BATCH):
        batch = items[i : i + BATCH]
        logger.info(f"stick_figure: промпты батч {i // BATCH + 1} ({len(batch)} шотов)")
        if progress_cb:
            try:
                progress_cb(f"Stick-figure: промпты {i + len(batch)}/{len(items)}")
            except Exception:
                pass
        batch_prompts = await _generate_prompts_batch(batch, topic, all_prompts)
        # Проход проверки/починки промптов перед дорогой генерацией картинок
        try:
            batch_prompts = await _verify_prompts_batch(batch_prompts, topic)
        except Exception as e:
            logger.warning(f"stick_figure: проверка промптов пропущена ({e})")
        all_prompts.extend(batch_prompts)
    return all_prompts


# ── FAL Flux Schnell ──────────────────────────────────────────────────────────

async def _download_with_retry(client: httpx.AsyncClient, url: str, attempts: int = 3) -> Optional[bytes]:
    for k in range(attempts):
        try:
            r = await client.get(url)
            if r.status_code == 200 and r.content:
                return r.content
        except Exception as e:
            logger.warning(f"stick download retry {k + 1}/{attempts}: {e}")
        await asyncio.sleep(1.5 * (k + 1))
    return None


async def _fal_generate_image(prompt: str, output_path: Path, sem: asyncio.Semaphore,
                              style_prefix: str = STYLE_PREFIX, allow_text: bool = False) -> bool:
    fal_key = os.getenv("FALAPI", "")
    if not fal_key:
        logger.warning("FALAPI не задан")
        return False

    cfg = get_image_config()
    extra = cfg.get("params") or DEFAULT_IMG_PARAMS
    headers = {"Authorization": f"Key {fal_key}", "Content-Type": "application/json"}

    ref = _char_ref_datauri()
    if ref:
        # image-to-image: референс держит стиль+персонажа, промпт = сама сцена.
        # Сцены — запрет любого текста; превью (allow_text) — текст разрешён (подпись).
        url = FAL_EDIT_URL
        parts = [_EDIT_STYLE_GUIDE, f"SCENE: {prompt}", _EDIT_SCENE_CLOSER]
        if not allow_text:  # сцены без текста; превью (allow_text) — подпись разрешена
            parts.append(_EDIT_NO_TEXT)
        full_prompt = "\n".join(parts)
        payload = {"prompt": full_prompt, "image_urls": [ref], **extra}
    else:
        url = cfg.get("endpoint") or FAL_QUEUE_URL
        full_prompt = f"{style_prefix}, {prompt}" if style_prefix else prompt
        payload = {"prompt": full_prompt, **extra}

    async with sem:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                image_url = ""
                if "images" in data:
                    image_url = data["images"][0].get("url", "")
                elif "request_id" in data:
                    request_id = data["request_id"]
                    status_url = data.get("status_url") or f"{url}/requests/{request_id}/status"
                    response_url = data.get("response_url") or f"{url}/requests/{request_id}"
                    for _ in range(90):
                        await asyncio.sleep(1)
                        sr = await client.get(status_url, headers={"Authorization": f"Key {fal_key}"})
                        sd = sr.json()
                        st = sd.get("status")
                        if st == "COMPLETED":
                            rr = await client.get(response_url, headers={"Authorization": f"Key {fal_key}"})
                            image_url = rr.json().get("images", [{}])[0].get("url", "")
                            break
                        if st in ("FAILED", "CANCELLED"):
                            return False
                    else:
                        logger.warning(f"FAL timeout: {output_path.stem}")
                        return False

                if not image_url:
                    return False

                content = await _download_with_retry(client, image_url)
                if content:
                    output_path.write_bytes(content)
                    return True
        except Exception as e:
            logger.error(f"FAL failed for {output_path.name}: {e}")
    return False


# ── Ken Burns ─────────────────────────────────────────────────────────────────

async def _apply_ken_burns_async(image_path: Path, output_path: Path, duration: float) -> Path:
    from backend.pipeline.image_gen import apply_ken_burns
    return await asyncio.to_thread(apply_ken_burns, image_path, output_path, duration)


def _make_static_clip(image_path: Path, output_path: Path, duration: float) -> None:
    """Статичный клип: картинка держится `duration` секунд БЕЗ zoompan — мгновенно
    (~0.5с/клип). Для мультяшного канала движение не нужно; zoompan давал ~30с/клип
    на слабом CPU (фильтр тяжёлый, ultrafast его не ускоряет)."""
    # БЕЗ scale-фильтра: картинки уже 2048×1152 (16:9), DaVinci впишет в 1920×1080 сам.
    # Это убирает фильтр на каждый кадр (быстрее). tune stillimage + ultrafast.
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", str(duration),
        "-r", "12", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "26", "-pix_fmt", "yuv420p", "-an", "-threads", "2", str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)


async def _static_clip_async(image_path: Path, output_path: Path, duration: float) -> Path:
    await asyncio.to_thread(_make_static_clip, image_path, output_path, duration)
    return output_path


# ── Расчёт slot_sec (зеркало download_clips:646-659) ──────────────────────────

def _compute_slots(shots: list[dict]) -> list[float]:
    slots: list[float] = []
    for i, shot in enumerate(shots):
        scene_dur = float(shot.get("end", 0) or 0) - float(shot.get("start", 0) or 0)
        if i + 1 < len(shots):
            slot = max(scene_dur, float(shots[i + 1].get("start", 0)) - float(shot.get("start", 0)))
        else:
            slot = scene_dur + 3.0  # последний: запас на хвост до конца голоса
        if slot > SLOT_CAP_SEC:
            logger.warning(f"stick shot {i+1}: slot {slot:.0f}s > {SLOT_CAP_SEC}s — обрезаю (битый alignment?)")
            slot = max(scene_dur, SLOT_CAP_SEC)
        slots.append(max(0.5, slot))
    return slots


def _split_text_evenly(text: str, n: int) -> list[str]:
    """Режет текст на n кусков ~равной длины по границам слов. СТАБИЛЬНО: тот же
    текст → те же куски (не зависит от длины голоса)."""
    words = text.split()
    if n <= 1 or len(words) <= 1:
        return [text]
    target = len(text) / n
    chunks: list[str] = []
    cur: list[str] = []
    cl = 0
    for w in words:
        cur.append(w)
        cl += len(w) + 1
        if cl >= target and len(chunks) < n - 1:
            chunks.append(" ".join(cur))
            cur, cl = [], 0
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [text]


def _stick_shots_by_text(scene_plan: list[dict], target_chars: int = 130) -> list[dict]:
    """Шоты стика = куски сцен по ТЕКСТУ (~target_chars), а НЕ по длине голоса.
    Стабильны между переозвучками/языками: тот же сценарий → те же куски в том же
    порядке → картинка stick_{k}.png переиспользуется при смене голоса. Тайминг куска =
    доля [start,end] сцены пропорционально длине его текста. Это убирает зависимость
    раскадровки от голоса (раньше split_scenes резал по длительности → нестабильно)."""
    shots: list[dict] = []
    for sc in scene_plan:
        text = (sc.get("text") or "").strip()
        s = float(sc.get("start", 0) or 0)
        e = float(sc.get("end", 0) or 0)
        dur = max(0.0, e - s)
        if not text or dur <= 0:
            shots.append({**sc, "start": s, "end": e})
            continue
        n = max(1, round(len(text) / target_chars))
        if n == 1:
            shots.append({**sc, "start": s, "end": e})
            continue
        chunks = _split_text_evenly(text, n)
        total = sum(len(c) for c in chunks) or 1
        t = s
        for c in chunks:
            ce = min(e, t + dur * len(c) / total)
            shots.append({**sc, "text": c, "start": round(t, 3), "end": round(ce, 3)})
            t = ce
        shots[-1]["end"] = e
    return shots


# ── Главная точка входа ───────────────────────────────────────────────────────

async def generate_stick_images_from_scene_plan(
    scene_plan: list[dict],
    topic: str,
    output_dir: Path,
    voiceover_duration: Optional[float] = None,
    progress_cb=None,
) -> list[dict]:
    """
    Генерирует stick-figure клипы для aligned scene_plan, повторяя тайминг download_clips.
    Возвращает clip_map совместимый с assembly.py. Инвариант: каждый шот → клип на slot_sec.
    """
    from backend.pipeline.clips import (
        _merge_short_scenes, split_scenes, _render_infographic, _ensure_slot_length,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Миграция legacy: старые сборки клали PNG в подпапку clips/. Теперь картинки
    # лежат РЯДОМ с project.fcpxml (output_dir = корень workspace), чтобы DaVinci
    # находил их при ручном импорте XML (как озвучку/музыку) — без Media Offline.
    # Переносим уже оплаченные PNG из clips/ в корень → пересборка БЕЗ регенерации.
    legacy = output_dir / "clips"
    if output_dir.name != "clips" and legacy.is_dir():
        moved = 0
        for old in list(legacy.glob("stick_*.png")) + [legacy / "_style_version.txt"]:
            dest = output_dir / old.name
            if old.exists() and not dest.exists():
                try:
                    old.replace(dest)
                    moved += 1
                except Exception:
                    pass
        if moved:
            logger.info(f"stick_figure: перенёс {moved} файлов из clips/ в корень (DaVinci-friendly)")

    # Инвалидация кэша при смене арт-стиля: если версия в sentinel != текущей,
    # удаляем старые PNG один раз → перегенерим в новом стиле. При совпадении версии
    # PNG переиспользуются в _gen_one (пересборки той же версии бесплатны).
    ver_file = output_dir / "_style_version.txt"
    prev_ver = ver_file.read_text(encoding="utf-8").strip() if ver_file.exists() else ""
    if prev_ver != STYLE_VERSION:
        wiped = 0
        for old in output_dir.glob("stick_*.png"):
            old.unlink(missing_ok=True)
            wiped += 1
        ver_file.write_text(STYLE_VERSION, encoding="utf-8")
        if wiped:
            logger.info(f"stick_figure: стиль {prev_ver or '∅'}→{STYLE_VERSION}, стёр {wiped} старых PNG → регенерация")

    def _cb(msg: str):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    # 1. Слияние коротких сцен + разбивка на шоты — ТА ЖЕ логика что у Pexels
    scene_plan = _merge_short_scenes(scene_plan)
    shots = split_scenes(scene_plan)
    slots = _compute_slots(shots)
    logger.info(f"stick_figure: {len(scene_plan)} сцен → {len(shots)} шотов")

    # 2. Какие шоты рисуем стиком (всё, кроме инфографики с реальными данными)
    stick_idx = [i for i, s in enumerate(shots) if not str(s.get("visual_type", "stock")).startswith("remotion_")]

    # 3. Промпты только для стик-шотов
    _cb(f"Stick-figure: промпты для {len(stick_idx)} сцен")
    stick_shots = [shots[i] for i in stick_idx]
    stick_prompts = await _generate_all_prompts(stick_shots, topic, progress_cb)

    # 4. Генерация PNG ПАРАЛЛЕЛЬНО (×10) с ретраями ВНУТРИ параллельной фазы —
    # чтобы сборка не залипала на последовательных ретраях сбойных картинок.
    _cb(f"Stick-figure: генерирую {len(stick_idx)} картинок (Seedream v4, параллельно ×10)")
    sem = asyncio.Semaphore(10)
    png_for_shot: dict[int, Optional[Path]] = {}
    prompt_for_shot: dict[int, str] = {
        shot_i: stick_prompts[k] for k, shot_i in enumerate(stick_idx)
    }
    done_n = 0

    async def _gen_one(shot_i: int, prompt: str, total: int):
        nonlocal done_n
        img_path = output_dir / f"stick_{shot_i:03d}.png"
        # Переиспользуем уже сгенеренную картинку (пересборка) — НЕ платим за неё дважды.
        if img_path.exists() and img_path.stat().st_size > 1000:
            png_for_shot[shot_i] = img_path
            done_n += 1
            return
        ok = False
        for _ in range(3):  # ретрай в ПАРАЛЛЕЛИ, не в цикле сборки
            if await _fal_generate_image(prompt or "a round-headed cartoon character in a cozy detailed room, warm light", img_path, sem):
                ok = True
                break
        png_for_shot[shot_i] = img_path if ok else None
        done_n += 1
        if done_n % 20 == 0:
            _cb(f"Stick-figure: {done_n}/{total} картинок")

    await asyncio.gather(*[
        _gen_one(shot_i, stick_prompts[k], len(stick_idx))
        for k, shot_i in enumerate(stick_idx)
    ])

    # 5. Кодируем КАЖДУЮ картинку в короткий статичный mp4 — как немецкий пайплайн.
    # DaVinci по FCPXML НЕ линкует сырые PNG-стиллы (Media Offline даже при указанной
    # папке), а mp4-клипы находит (de так и работает). Статика без Ken Burns → быстро,
    # параллельно ×4. PNG остаются как источник (reuse без регенерации Seedream).
    _cb(f"Stick-figure: кодирую {len(stick_idx)} клипов в mp4")
    enc_sem = asyncio.Semaphore(4)
    mp4_for_shot: dict[int, Optional[Path]] = {}
    enc_done = 0

    async def _enc_one(shot_i: int, total: int):
        nonlocal enc_done
        png = png_for_shot.get(shot_i)
        mp4 = output_dir / f"stick_{shot_i:03d}.mp4"
        slot = float(slots[shot_i]) if shot_i < len(slots) else 4.0
        if png and png.exists():
            async with enc_sem:
                try:
                    await _static_clip_async(png, mp4, max(0.5, slot))
                except Exception as e:
                    logger.warning(f"stick encode {shot_i}: {e}")
            mp4_for_shot[shot_i] = mp4 if (mp4.exists() and mp4.stat().st_size > 1000) else None
        else:
            mp4_for_shot[shot_i] = None
        enc_done += 1
        if enc_done % 20 == 0:
            _cb(f"Stick-figure: {enc_done}/{total} клипов")

    await asyncio.gather(*[_enc_one(i, len(stick_idx)) for i in stick_idx])

    # 6. clip_map ссылается на mp4-клипы → fcpxml пишет их как <asset-clip> (видео),
    # которые DaVinci линкует. Дыра (сбой кодирования) → соседний готовый mp4.
    ordered = [mp4_for_shot.get(i) for i in range(len(shots))]
    first_good = next((p for p in ordered if p and p.exists()), None)
    if first_good is None:
        raise RuntimeError("stick_figure: ни одного клипа не закодировалось — проверь ffmpeg/FALAPI")
    clip_map: list[dict] = []
    last_good = first_good
    holes = 0
    for i, shot in enumerate(shots):
        mp4 = ordered[i]
        if mp4 and mp4.exists():
            last_good = mp4
            clip_map.append(_entry(mp4, "stick_clip", slots[i], shot, prompt_for_shot.get(i, "")))
        else:
            holes += 1
            clip_map.append(_entry(last_good, "stick_clip_reuse", slots[i], shot))
    logger.info(f"stick_figure: {len(clip_map)} mp4-клипов ({holes} дыр заполнено)")

    # scene_prompts.json — структурированный список визуал-промптов по сценам (клиент
    # просил JSON: удобно просматривать/править перед регенерацией). Это РЕВЬЮ-артефакт;
    # на саму генерацию не влияет (Seedream ест строку), влияет арт-стиль промпта.
    try:
        prompts_json = [
            {
                "index": i,
                "image": Path(c["path"]).name,
                "start": round(float(c.get("scene_start", 0)), 2),
                "end": round(float(c.get("scene_end", 0)), 2),
                "slot_sec": round(float(c.get("slot_sec", 0)), 2),
                "source": c.get("source", ""),
                "prompt": c.get("scene_text", ""),
            }
            for i, c in enumerate(clip_map)
        ]
        (output_dir / "scene_prompts.json").write_text(
            json.dumps(prompts_json, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"scene_prompts.json не записан: {e}")

    return clip_map


async def retime_clip_map(workspace: Path, clip_map: list[dict], new_voice_dur: float,
                          progress_cb=None) -> list[dict]:
    """Переозвучка С СОХРАНЕНИЕМ картинок (то, что просил клиент: «голос только заменить»).
    Масштабируем тайминги готового clip_map под НОВУЮ длину голоса (factor = D_new/D_old)
    и пере-кодируем ТЕ ЖЕ картинки (stick_k.png) в mp4 на новую длину клипа. БЕЗ Seedream,
    без перепланировки — те же кадры и музыка, новый голос и тайминги."""
    def _cb(m: str):
        if progress_cb:
            try:
                progress_cb(m)
            except Exception:
                pass

    d_old = max((float(c.get("scene_end", 0) or 0) for c in clip_map), default=0.0)
    factor = (new_voice_dur / d_old) if (d_old > 0 and new_voice_dur > 0) else 1.0
    _cb(f"Переозвучка: пере-присобачиваю {len(clip_map)} картинок ×{factor:.2f} (без регенерации)")
    sem = asyncio.Semaphore(4)
    done = 0
    indexed: list[tuple[int, dict]] = []

    async def _one(i: int, c: dict):
        nonlocal done
        ns = float(c.get("scene_start", 0) or 0) * factor
        ne = float(c.get("scene_end", 0) or 0) * factor
        slot = (ne - ns) if ne > ns else float(c.get("slot_sec", 4) or 4) * factor
        slot = max(0.5, slot)
        clip_path = Path(c["path"])
        if clip_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            png, mp4 = clip_path, clip_path.with_suffix(".mp4")
        else:
            png, mp4 = clip_path.with_suffix(".png"), clip_path
        if png.exists():
            async with sem:
                try:
                    await _static_clip_async(png, mp4, slot)
                except Exception as e:
                    logger.warning(f"retime encode {i}: {e}")
        nc = {**c, "path": str(mp4), "scene_start": round(ns, 3), "scene_end": round(ne, 3),
              "slot_sec": round(slot, 3), "duration": round(slot, 3)}
        indexed.append((i, nc))
        done += 1
        if done % 20 == 0:
            _cb(f"Переозвучка: {done}/{len(clip_map)} кадров")

    await asyncio.gather(*[_one(i, c) for i, c in enumerate(clip_map)])
    indexed.sort(key=lambda x: x[0])
    out = [c for _, c in indexed]
    logger.info(f"retime_clip_map: {len(out)} клипов ×{factor:.2f}, картинки те же (без регенерации)")
    return out


async def generate_thumbnail(topic: str, lang: str, output_dir: Path,
                             hook_text: str = "") -> Optional[Path]:
    """Авто-превью (обложка): тем же Seedream рисует кликабельный thumbnail — крупное
    эмоциональное лицо персонажа + короткий заголовок на языке канала (2-4 слова).
    Текст Seedream рендерит чисто. Best-effort: при сбое не валит сборку."""
    out = output_dir / "thumbnail.png"
    if out.exists() and out.stat().st_size > 1000:
        return out
    lang_names = {"de": "German", "es": "Spanish", "en": "English", "vi": "Vietnamese"}
    ln = lang_names.get(lang, lang)
    try:
        model_cfg = get_model_config("scene_tagging")
        spec = await call_llm(
            prompt=f"""You design ONE click-worthy YouTube thumbnail for a warm curiosity video titled "{topic}".
Output ONE single line (English description) in EXACTLY this shape:
a simple stick-figure SCENE showing the EMOTIONAL HEART of this topic — 1 to 3 round-headed stick figures with a strong, exaggerated emotion (curious / amazed / scared / cozy / awkward) doing the one relatable thing the video is about, plus one or two simple props OR a contrasting element that hints at the stakes; mood color matching the topic (warm and bright if cozy/positive, dark and moody browns/blues if danger/tension); a big bold {ln} caption across the TOP reading "<A PUNCHY 2-3 WORD {ln} CURIOSITY QUESTION>" in a thick rounded hand-drawn sans-serif, bright YELLOW letters with a thick black outline.
The {ln} caption must be a SHORT, curiosity-driven QUESTION or punch (NOT the full video title) — e.g. the {ln} equivalent of "SURVIVED HOW?", "COZY ALL DAY?", "NO PRIVACY?". Output ONLY that one line, no quotes around the whole line.""",
            model=model_cfg["primary"], temperature=0.7, max_tokens=160,
        )
        spec = _strip_markdown(spec or "").strip()
        if not spec:
            return None
        if await _fal_generate_image(spec, out, asyncio.Semaphore(1), style_prefix=THUMB_STYLE, allow_text=True):
            logger.info(f"thumbnail сгенерирован: {out.name}")
            return out
    except Exception as e:
        logger.warning(f"generate_thumbnail не удался (best-effort): {e}")
    return None


async def generate_doodle_prompts(scenes: list[dict], topic: str) -> list[str]:
    """Промпты дудлов для списка сцен (для unified-режима — download_clips зовёт это
    одним батчем на все doodle-сцены). Возвращает список, выровненный по scenes."""
    if not scenes:
        return []
    return await _generate_all_prompts(scenes, topic)


_DOODLE_SEM = asyncio.Semaphore(6)


async def render_doodle(prompt: str, slot_sec: float, clip_path: Path) -> bool:
    """Одна дудл-сцена для unified-пайплайна: FAL Schnell (наш стиль+промпт) → Ken Burns
    на slot_sec. True при успехе. Картинку чистим после рендера."""
    img = clip_path.with_suffix(".doodle.png")
    if not await _fal_generate_image(prompt or "a round-headed cartoon character thinking in a cozy detailed room, warm light", img, _DOODLE_SEM):
        return False
    try:
        await _apply_ken_burns_async(img, clip_path, slot_sec)
        return True
    except Exception as e:
        logger.error(f"render_doodle Ken Burns: {e}")
        return False
    finally:
        img.unlink(missing_ok=True)


def _entry(path: Path, source: str, slot: float, shot: dict, prompt: str | None = None) -> dict:
    """clip_map-запись в формате download_clips/assembly.

    Для стик-шотов scene_text = реальный промпт, которым рисовали (motion-notes
    покажет что НА САМОМ ДЕЛЕ нарисовано, а не on_screen родительской сцены)."""
    return {
        "scene_index": shot.get("scene_index", 0),
        "path": str(path),
        "query": source,
        "search_query": source,
        "source": source,
        "duration": slot,
        "slot_sec": slot,
        "scene_start": shot.get("start", 0),
        "scene_end": shot.get("end", 0),
        "mood": shot.get("mood", "neutral"),
        "scene_text": prompt or shot.get("on_screen") or shot.get("text", ""),
        "text_overlay": shot.get("text_overlay", ""),
    }
