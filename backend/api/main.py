"""
YouTube Factory — FastAPI backend.

Endpoints:
  GET  /api/v1/health
  GET  /api/v1/channels                — list channel profiles
  GET  /api/v1/channels/{lang}         — get channel details + history
  POST /api/v1/channels/{lang}/discover — discover viral topics for channel
  POST /api/v1/videos                  — create video generation task
  GET  /api/v1/videos                  — list all tasks
  GET  /api/v1/videos/{task_id}        — get task status
  GET  /api/v1/videos/{task_id}/download — download final mp4
  DELETE /api/v1/videos/{task_id}      — cancel task
  GET  /api/v1/music                   — list music library
  WS   /api/v1/ws/{task_id}            — real-time progress
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import (
    OUTPUT_DIR, DATA_DIR, load_yaml, get_channel_config,
    get_channel_history, get_music_library, add_to_channel_history,
    get_topic_archive, save_topics_to_archive, mark_topic_used,
    get_published_titles, now_iso,
)
from backend.scrapers.trending import _drop_published_ideas
from backend.api.models import (
    CreateVideoRequest, VideoResponse, TopicDiscoverRequest,
    TopicDiscoverResponse, TopicIdea, ChannelInfo, MusicTrack,
    VoiceInfo, ThemeInfo, HealthResponse, MetadataResponse,
    ApproveScriptRequest, TranslateVideoRequest,
)
from backend.api.static import mount_static

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Factory API",
    description="Automated multilingual YouTube video generation",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Доступ только владельцу: пароль на /api/* (кроме /health) ──
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "")


@app.middleware("http")
async def _auth_gate(request, call_next):
    path = request.url.path
    # пускаем без пароля: статику фронта, healthcheck; защищаем только /api/*
    if (SITE_PASSWORD and path.startswith("/api/")
            and not path.startswith("/api/v1/health")):
        # пароль из хедера ИЛИ query-param pw (для download через window.open)
        given = request.headers.get("X-Site-Password", "") or request.query_params.get("pw", "")
        if given != SITE_PASSWORD:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


_MEDIA_SUFFIXES = {".mp4", ".mp3", ".wav", ".png", ".jpg", ".jpeg"}


def _strip_workspace_media(ws: Path) -> int:
    """Удалить тяжёлые медиа из workspace (клипы/аудио), СОХРАНИВ checkpoint.json,
    metadata, PUBLISH, сценарии и fcpxml — листинг задач и метадата продолжают работать.
    Возвращает освобождённые байты. Зовётся для completed-задач: их zip уже собран."""
    freed = 0
    try:
        for p in ws.rglob("*"):
            if p.is_file() and p.suffix.lower() in _MEDIA_SUFFIXES:
                try:
                    freed += p.stat().st_size
                    p.unlink()
                except Exception:
                    pass
        clips = ws / "clips"
        if clips.exists() and not any(clips.iterdir()):
            clips.rmdir()
    except Exception:
        pass
    return freed


def _ensure_free_space(min_gb: float = 3.0, exclude: set = None):
    """Перед стартом задачи: прогон пишет ~2-3ГБ. Если свободного меньше min_gb —
    удаляем СТАРЕЙШИЕ zip-ы готовых видео. min_gb ОБЯЗАН быть меньше размера тома
    (5ГБ): порог 5.0 на 5ГБ-томе срабатывал всегда и удалял ВСЕ zip-ы при каждом
    старте. exclude — zip-ы, которые трогать нельзя (источник пересборки)."""
    try:
        free = shutil.disk_usage(OUTPUT_DIR).free
        if free >= min_gb * 1024**3:
            return
        zips = sorted(OUTPUT_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        if exclude:
            zips = [z for z in zips if z not in exclude]
        # КРИТИЧНО: удаляем ТОЛЬКО уже СКАЧАННЫЕ клиентом zip (есть маркер .downloaded,
        # ставится в download_video). Не скачанный zip — работа клиента, которую он ещё
        # не забрал → НИКОГДА не удаляем автоматически. Раньше сносили старейшие подряд
        # и теряли не скачанные видео.
        # КРИТИЧНО: удаляем зип только если он (1) скачан клиентом (маркер .downloaded)
        # И (2) старше 12 часов. Маркер ставится на КЛИК «скачать», а не на реально
        # сохранённый файл — случайный/прерванный клик не должен стоить клиенту видео.
        # 12ч-грейс держит свежий зип живым, пока клиент его реально не заберёт. Не
        # скачанные зипы — НИКОГДА не трогаем.
        import time as _t
        _now = _t.time()
        zips = [z for z in zips
                if Path(str(z) + ".downloaded").exists()
                and (_now - z.stat().st_mtime) > 12 * 3600]
        if not zips:
            logger.warning(
                "space-guard: мало места, но нет скачанных зипов старше 12ч — "
                "НИЧЕГО не удаляю (не теряем свежую/не скачанную работу). "
                "Освободи место в библиотеке вручную (кнопка удаления).")
            return
        for z in zips:
            try:
                sz = z.stat().st_size
                z.unlink()
                Path(str(z) + ".downloaded").unlink(missing_ok=True)
                free += sz
                logger.info(f"space-guard: удалён СКАЧАННЫЙ zip {z.name} ({sz/1024/1024:.0f} MB)")
            except Exception:
                continue
            if free >= min_gb * 1024**3:
                break
    except Exception as e:
        logger.warning(f"space-guard пропущен: {e}")


# файл-маркеры готовности фаз — для восстановления битого checkpoint.json
# ПОРЯДОК ВАЖЕН: отражает новый порядок пайплайна (voiceover → scene_planning)
_PHASE_FILE_MARKERS = [
    ("script_generation", "script.txt"),
    ("script_improvement", "improved_script.txt"),
    ("virality_filter", "viral_script.txt"),
    ("voiceover", "voiceover.mp3"),           # ← TTS first
    ("scene_planning", "scene_plan.json"),    # ← after TTS
    ("alignment", "scene_plan_aligned.json"),
    ("clip_download", "clip_map.json"),
    ("music", "music.mp3"),
    # assembly: fcpxml mode OR rendered mode (final_*.mp4)
    ("assembly", "project.fcpxml"),
]


def _assembly_done(ws: Path) -> bool:
    """True if assembly phase completed — works for both fcpxml and rendered modes."""
    return (ws / "project.fcpxml").exists() or bool(list(ws.glob("final_*.mp4")))


def _reconstruct_checkpoint(ws: Path) -> bool:
    """checkpoint.json побился (запись на полный диск обрывается) → задача невидима,
    а её файлы (сценарий, озвучка) целы. Восстанавливаем состояние по файлам-маркерам,
    чтобы Retry продолжил с места, не переделывая дорогие фазы (LLM/TTS)."""
    try:
        flags = {}
        for phase, fname in _PHASE_FILE_MARKERS:
            if phase == "assembly":
                if _assembly_done(ws):
                    flags[phase] = True
            elif (ws / fname).exists():
                flags[phase] = True
        if not flags:
            return False
        parts = ws.name.rsplit("_", 2)
        task_id = parts[-1] if len(parts) >= 2 else ws.name
        lang = parts[-2] if len(parts) >= 3 else "de"
        # незавершённый clip_download → недокачанные клипы только занимают место
        if "clip_download" not in flags:
            clips = ws / "clips"
            if clips.exists():
                for p in clips.glob("*"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
        # detect mode from files: fcpxml marker takes priority, else rendered mp4
        output_mode = "fcpxml" if (ws / "project.fcpxml").exists() else (
            "rendered" if list(ws.glob("final_*.mp4")) else "fcpxml"
        )
        # visual_mode: сначала доверяем сохранённому в checkpoint (надёжно), и только
        # если его там нет — sniff по следам стик-клипов (битый checkpoint мог потерять).
        clips_dir = ws / "clips"
        _existing_vm = (_read_checkpoint(ws) or {}).get("visual_mode")
        visual_mode = _existing_vm or ("stick_figure" if (
            clips_dir.exists() and (any(clips_dir.glob("stick_*.png")) or any(clips_dir.glob("stick_clip_*.mp4")))
        ) else "pexels")
        _update_checkpoint(ws, {
            "task_id": task_id,
            "topic": ws.name.rsplit("_", 2)[0].replace("_", " ").strip() or ws.name,
            "lang": lang,
            "output_mode": output_mode,
            "visual_mode": visual_mode,
            "status": "failed",
            "current_phase": next((p for p, _ in reversed(_PHASE_FILE_MARKERS) if flags.get(p)), ""),
            "checkpoint": flags,
            "error": "checkpoint был повреждён (диск переполнился) — готовые фазы сохранены, нажми «Продолжить»",
        })
        logger.info(f"reconstructed checkpoint: {ws.name} ({len(flags)} фаз готово)")
        return True
    except Exception as e:
        logger.warning(f"reconstruct {ws.name} failed: {e}")
        return False


@app.on_event("startup")
async def _recover_orphans():
    """При старте: (0) увеличить thread-pool под asyncio.to_thread (параллельные
    ffmpeg/render/скачивание клипов); (1) чистка диска — том маленький, прогон тяжёлый;
    (2) зависшие running/scripting/pending → failed, чтобы продолжить кнопкой Retry.
    Каждый шаг изолирован: полный диск НЕ должен ронять приложение."""
    try:
        # Дефолтный executor — min(32, cpu+4); под параллельные to_thread (ffmpeg=4 +
        # render=2 + fal=4 + валидация) поднимаем до 16, чтобы офлоады не вставали в
        # очередь друг за другом. Реальную конкуренцию ограничивают семафоры в clips.py.
        asyncio.get_running_loop().set_default_executor(
            concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="clip-io"))
    except Exception:
        pass
    # Прогрев кэша опубликованных видео канала (бейдж «уже на канале») в ФОНЕ —
    # чтобы on_channel считался из 12ч disk-кэша, без сети на hot-path. Не блокируем старт.
    async def _warm_published():
        for _lang in ("de", "es"):
            try:
                await asyncio.to_thread(get_published_titles, _lang)
            except Exception:
                pass
    try:
        asyncio.create_task(_warm_published())
    except Exception:
        pass
    try:
        if not OUTPUT_DIR.exists():
            return
        freed = 0
        zips = []
        for ws in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime):
            try:
                if ws.is_file() and ws.suffix == ".zip":
                    zips.append(ws)
                    continue
                if not ws.is_dir():
                    continue
                cp = _read_checkpoint(ws)
                status = (cp or {}).get("status", "")
                if not cp:
                    _reconstruct_checkpoint(ws)
                    continue
                if status == "cancelled":
                    freed += _strip_workspace_media(ws)
                elif status == "completed":
                    # zip собран и лежит рядом — сырые медиа в workspace не нужны
                    freed += _strip_workspace_media(ws)
                elif status in ("running", "scripting", "pending"):
                    try:
                        _update_checkpoint(ws, {
                            "status": "failed",
                            "error": "Прервано рестартом сервера — нажми «Продолжить с места ошибки»",
                        })
                        logger.info(f"recovered orphan task → failed: {ws.name}")
                    except Exception as e:
                        logger.warning(f"recover {ws.name} failed: {e}")
            except Exception:
                continue
        # держим только 2 свежих zip-а (самые тяжёлые артефакты на томе)
        for z in zips[:-2]:
            try:
                freed += z.stat().st_size
                z.unlink()
                logger.info(f"cleanup: удалён старый zip {z.name}")
            except Exception:
                pass
        if freed:
            logger.info(f"startup cleanup: освобождено {freed / 1024 / 1024:.0f} MB")
    except Exception as e:
        logger.warning(f"orphan recovery skipped: {e}")


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

_running_tasks: Dict[str, asyncio.Task] = {}

PIPELINE_PHASES = [
    "script_generation", "script_improvement", "virality_filter",
    "voiceover", "scene_planning", "alignment", "clip_download",
    "music", "assembly", "metadata", "delivery",
]


def _phase_progress(checkpoint: dict) -> float:
    total = len(PIPELINE_PHASES)
    done = sum(1 for p in PIPELINE_PHASES if checkpoint.get(p))
    return round(done / total * 100, 1)


def _read_checkpoint(workspace: Path) -> Optional[dict]:
    cp = workspace / "checkpoint.json"
    if not cp.exists():
        return None
    try:
        with open(cp) as f:
            return json.load(f)
    except Exception:
        return None


def _checkpoint_to_response(cp: dict, workspace: Path) -> VideoResponse:
    task_id = cp.get("task_id", "")
    status = cp.get("status", "unknown")
    checkpoint_data = cp.get("checkpoint", {})

    download_url = None
    zip_candidate = workspace.parent / f"{workspace.name}.zip"
    has_output = zip_candidate.exists() or bool(list(workspace.glob("final_*.mp4")))
    if has_output and status == "completed":
        download_url = f"/api/v1/videos/{task_id}/download"

    # Extract metadata if available
    metadata = cp.get("metadata", {})

    # «Уже на YouTube?»: кэш из чекпоинта; если не посчитан (старые черновики) —
    # считаем для script_ready по СПИСКУ опубликованных (get_published_titles
    # держит свой 12-часовой disk-кэш + прогрев на старте → это быстрый путь, без
    # сети на каждый запрос).
    on_channel = bool(cp.get("on_channel", False))
    if not on_channel and status == "script_ready":
        try:
            topic = cp.get("topic", "")
            pub = get_published_titles(cp.get("lang", ""))
            on_channel = bool(topic and pub and not _drop_published_ideas(
                [{"title_original": topic}], pub))
        except Exception:
            pass

    return VideoResponse(
        task_id=task_id,
        topic=cp.get("topic", ""),
        lang=cp.get("lang", ""),
        on_channel=on_channel,
        improve_note=cp.get("improve_note"),
        status=status,
        current_phase=cp.get("current_phase", ""),
        phase_detail=cp.get("phase_detail"),
        progress_percent=_phase_progress(checkpoint_data),
        created_at=cp.get("created_at"),
        updated_at=cp.get("updated_at"),
        error=cp.get("error"),
        download_url=download_url,
        workspace=workspace.name,
        checkpoint=checkpoint_data,
        titles=metadata.get("titles"),
        titles_ru=metadata.get("titles_ru"),
        description=metadata.get("description"),
        tags=metadata.get("tags"),
        script_score=cp.get("script_score"),
        script_ru=cp.get("script_ru"),
        script_de=cp.get("script_de"),
        script_rubric=cp.get("script_rubric"),
    )


def _find_workspace_by_task_id(task_id: str) -> Optional[Path]:
    for ws in OUTPUT_DIR.iterdir():
        if not ws.is_dir():
            continue
        cp = _read_checkpoint(ws)
        if cp and cp.get("task_id") == task_id:
            return ws
    return None


async def _run_pipeline(task_id: str, req: CreateVideoRequest, workspace: Path):
    from backend.pipeline.orchestrator import Pipeline, VideoTask

    task = VideoTask(
        topic=req.topic,
        lang=req.lang,
        duration_minutes=req.duration_minutes,
        style=req.style,
        music_mood=req.music_mood,
        output_mode=req.output_mode,
        tts_mode=req.tts_mode,
        visual_mode=_resolve_visual_mode(getattr(req, "visual_mode", None), req.lang),
        task_id=task_id,
        workspace=workspace,
    )
    task.status = "running"
    task.save_checkpoint()

    pipeline = Pipeline()
    try:
        await pipeline.run(task, skip_completed=True)
        # Add to channel history on success
        add_to_channel_history(req.lang, req.topic)
    except Exception as exc:
        logger.error(f"Pipeline failed for {task_id}: {exc}")
        if task.status != "failed":
            task.status = "failed"
            task.error = str(exc)
            task.save_checkpoint()
    finally:
        _running_tasks.pop(task_id, None)



# (старый recover_orphaned_tasks удалён: дублировал _recover_orphans и БЕЗ try/except
#  ронял всё приложение на старте при полном диске — json.dump падал с ENOSPC)

# ── Channel endpoints ──

def _resolve_visual_mode(req_vm, lang: str) -> str:
    """visual_mode для прогона. Если запрос не задал явно (UI его не шлёт) — берём
    дефолт канала из channels.yaml (vi/es → stick_figure, de → pexels). Так канал
    становится цельно-мультяшным без тумблера в UI."""
    if req_vm and req_vm != "pexels":
        return req_vm
    try:
        ch_vm = (get_channel_config(lang) or {}).get("visual_mode")
    except Exception:
        ch_vm = None
    return ch_vm or "pexels"


@app.get("/api/v1/channels", response_model=list[ChannelInfo], tags=["channels"])
async def list_channels():
    """List all configured channels."""
    config = load_yaml("channels")
    channels = config.get("channels", {})
    result = []
    for lang, ch in channels.items():
        history = get_channel_history(lang)
        result.append(ChannelInfo(
            lang=lang,
            name=ch["name"],
            niche=ch["niche"],
            description=ch.get("description", ""),
            voice_id=ch.get("voice_id", ""),
            style=ch.get("style", "documentary"),
            duration_minutes=ch.get("duration_minutes", 22),
            history_window=ch.get("history_window", 10),
            recent_topics=history,
            total_videos=len(history) if history else 0,
        ))
    return result


@app.get("/api/v1/channels/{lang}", response_model=ChannelInfo, tags=["channels"])
async def get_channel(lang: str):
    """Get channel details including history."""
    try:
        ch = get_channel_config(lang)
    except ValueError:
        raise HTTPException(404, f"Channel {lang} not found")
    history = get_channel_history(lang)
    return ChannelInfo(
        lang=lang,
        name=ch["name"],
        niche=ch["niche"],
        description=ch.get("description", ""),
        voice_id=ch.get("voice_id", ""),
        style=ch.get("style", "documentary"),
        duration_minutes=ch.get("duration_minutes", 22),
        history_window=ch.get("history_window", 10),
        recent_topics=history,
        total_videos=len(history) if history else 0,
    )


@app.post("/api/v1/channels/{lang}/discover", response_model=TopicDiscoverResponse, tags=["channels"])
async def discover_channel_topics(lang: str, req: TopicDiscoverRequest):
    """Discover viral topics for a specific channel with Russian translations."""
    from backend.scrapers.trending import find_viral_topics

    # Не запускаем поиск тем во время активной сборки — discovery тяжёлый и крал бы
    # event-loop/CPU у сборки видео (тормозило скачивание клипов).
    if any(not t.done() for t in _running_tasks.values()):
        raise HTTPException(409, "Идёт сборка видео — поиск тем временно недоступен, "
                                 "чтобы не тормозить сборку. Попробуй после её завершения.")

    try:
        ch = get_channel_config(lang)
    except ValueError:
        raise HTTPException(404, f"Channel {lang} not found")

    try:
        result = await find_viral_topics(lang=lang, num_ideas=req.num_ideas)
    except Exception as exc:
        logger.error(f"Topic discovery failed: {exc}")
        raise HTTPException(500, str(exc))

    raw_ideas = [i for i in result.get("ideas", []) if isinstance(i, dict)]

    # Персистим найденные темы в архив (дедуп по id) — чтобы не искать заново
    # и не терять при рестарте. Возвращаем ВЕСЬ архив, отсортированный по скорингу.
    try:
        archived = save_topics_to_archive(lang, raw_ideas)
    except Exception as e:
        logger.warning(f"topic archive save failed: {e}")
        archived = raw_ideas

    # Дедуп против опубликованного на канале — фильтруем ВЕСЬ архив (в нём могли
    # осесть темы из старых запусков до дедупа, напр. VW/Siemens, которые уже на канале)
    archived = _drop_published_ideas(archived, get_published_titles(lang))

    ideas = [TopicIdea(
        id=idea.get("id", ""),
        status=idea.get("status", "new"),
        title_original=idea.get("title_original", ""),
        title_ru=idea.get("title_ru", ""),
        category=idea.get("category", ""),
        hook=idea.get("hook", ""),
        hook_ru=idea.get("hook_ru", ""),
        virality_score=idea.get("virality_score", 50),
        why_viral=idea.get("why_viral", ""),
        source_video=idea.get("source_video"),
        source_views=idea.get("source_views"),
    ) for idea in archived]

    return TopicDiscoverResponse(
        ideas=ideas,
        pattern_analysis=result.get("pattern_analysis"),
        channel_name=ch["name"],
        niche=ch["niche"],
        recent_topics=result.get("recent_topics", []),
    )


@app.get("/api/v1/channels/{lang}/topics", response_model=list[TopicIdea], tags=["channels"])
async def list_archived_topics(lang: str, include_used: bool = True):
    """Архив ранее отобранных тем (без повторного поиска/LLM). По убыванию скоринга."""
    topics = get_topic_archive(lang)
    topics = _drop_published_ideas(topics, get_published_titles(lang))  # скрыть уже опубликованное на канале
    if not include_used:
        topics = [t for t in topics if t.get("status") != "used"]
    return [TopicIdea(
        id=t.get("id", ""), status=t.get("status", "new"),
        title_original=t.get("title_original", ""), title_ru=t.get("title_ru", ""),
        category=t.get("category", ""), hook=t.get("hook", ""), hook_ru=t.get("hook_ru", ""),
        virality_score=t.get("virality_score", 50), why_viral=t.get("why_viral", ""),
        source_video=t.get("source_video"), source_views=t.get("source_views"),
    ) for t in topics]


# ── Music library ──

@app.get("/api/v1/music", response_model=list[MusicTrack], tags=["music"])
async def list_music():
    """List manually curated music tracks."""
    tracks = get_music_library()
    return [MusicTrack(**t) for t in tracks if isinstance(t, dict)]


# ── Video endpoints ──

@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse(
        status="ok", version="1.1.0",
        commit=os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:9])


# ── Референс-картинка персонажа (i2i): идёт в КАЖДУЮ сцену stick-каналов ──
# Загруженный клиентом файл кладётся на том (переживает деплой) и приоритетнее
# дефолта в образе. Картинка одна на все мультяшные каналы (единый стиль рисовки).
REFERENCE_PATH = DATA_DIR / "reference" / "char_ref.png"            # том
BAKED_REF_PATH = Path(__file__).parent.parent / "assets" / "char_ref.png"  # дефолт в образе


def _active_reference() -> Path | None:
    for p in (REFERENCE_PATH, BAKED_REF_PATH):
        try:
            if p.exists() and p.stat().st_size > 1000:
                return p
        except OSError:
            continue
    return None


@app.get("/api/v1/reference-image/info", tags=["system"])
async def reference_image_info():
    """Статус референса: загружен ли клиентом свой, активен ли вообще, размер."""
    custom = REFERENCE_PATH.exists() and REFERENCE_PATH.stat().st_size > 1000
    active = _active_reference()
    return {
        "custom": bool(custom),
        "active": bool(active),
        "size": active.stat().st_size if active else 0,
        "source": "uploaded" if custom else ("default" if active else "none"),
    }


@app.get("/api/v1/reference-image", tags=["system"])
async def get_reference_image():
    """Отдать текущий активный референс (для предпросмотра на сайте)."""
    p = _active_reference()
    if not p:
        raise HTTPException(status_code=404, detail="Референс не задан")
    return FileResponse(str(p), media_type="image/png")


@app.post("/api/v1/reference-image", status_code=202, tags=["system"])
async def upload_reference_image(file: UploadFile = File(...)):
    """Загрузить картинку-референс персонажа. Подхватится следующей сборкой
    (i2i во всех сценах stick-каналов), без передеплоя."""
    raw = await file.read()
    if len(raw) < 1000:
        raise HTTPException(status_code=400, detail="Файл пустой или слишком маленький")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Картинка больше 12 МБ — ужми")
    is_png = raw[:8].startswith(b"\x89PNG")
    is_jpg = raw[:3] == b"\xff\xd8\xff"
    is_webp = raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"
    if not (is_png or is_jpg or is_webp):
        raise HTTPException(status_code=400, detail="Нужен PNG, JPG или WEBP")
    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_PATH.write_bytes(raw)
    logger.info(f"reference-image: загружен новый референс ({len(raw)} байт)")
    return {"ok": True, "size": len(raw), "filename": file.filename}


@app.post("/api/v1/videos", response_model=VideoResponse, status_code=202, tags=["videos"])
async def create_video(req: CreateVideoRequest):
    _ensure_free_space()
    from backend.pipeline.orchestrator import VideoTask

    # Check topic not in recent history
    recent = get_channel_history(req.lang)
    channel = get_channel_config(req.lang)
    window = channel.get("history_window", 10)
    recent_window = recent[-window:] if recent else []

    # Warn but don't block (might be intentional)
    topic_lower = req.topic.lower()
    for rt in recent_window:
        if rt.lower() == topic_lower:
            logger.warning(f"Topic '{req.topic}' was recently used on {req.lang} channel")

    seed_task = VideoTask(
        topic=req.topic,
        lang=req.lang,
        duration_minutes=req.duration_minutes,
        style=req.style,
        music_mood=req.music_mood,
        output_mode=req.output_mode,
        tts_mode=req.tts_mode,
    )
    task_id = seed_task.task_id
    workspace = seed_task.workspace

    seed_task.status = "pending"
    seed_task.current_phase = ""
    cp_path = workspace / "checkpoint.json"
    with open(cp_path, "w") as f:
        json.dump({
            "task_id": task_id,
            "topic": req.topic,
            "lang": req.lang,
            "duration_minutes": req.duration_minutes,
            "style": req.style,
            "music_mood": req.music_mood,
            "output_mode": req.output_mode,
            "tts_mode": req.tts_mode,
            "status": "pending",
            "current_phase": "",
            "checkpoint": {},
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, f, indent=2)

    coro = _run_pipeline(task_id, req, workspace)
    bg_task = asyncio.create_task(coro)
    _running_tasks[task_id] = bg_task

    cp = _read_checkpoint(workspace)
    return _checkpoint_to_response(cp, workspace)


# ── Script approval gate ──

def _update_checkpoint(workspace: Path, updates: dict):
    """Атомарный merge доп.ключей в checkpoint.json (балл, перевод, статус)."""
    cp_path = workspace / "checkpoint.json"
    data = {}
    if cp_path.exists():
        try:
            data = json.loads(cp_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.update(updates)
    data["updated_at"] = now_iso()
    tmp = cp_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cp_path)


async def _run_script_draft(task_id: str, req: CreateVideoRequest, workspace: Path):
    from backend.pipeline.orchestrator import Pipeline, VideoTask
    from backend.pipeline.script import assess_script
    task = VideoTask(
        topic=req.topic, lang=req.lang, duration_minutes=req.duration_minutes,
        style=req.style, music_mood=req.music_mood, output_mode=req.output_mode,
        tts_mode=req.tts_mode, visual_mode=_resolve_visual_mode(getattr(req, "visual_mode", None), req.lang),
        source_transcript=getattr(req, "source_transcript", None),
        task_id=task_id, workspace=workspace,
    )
    task.status = "running"
    task.save_checkpoint()
    try:
        await Pipeline().run(task, stop_after="virality_filter")
        sp = task.improved_script_path or task.script_path
        script_text = Path(sp).read_text(encoding="utf-8")
        a = await assess_script(script_text, req.lang)
        # «Уже на YouTube?» считаем ОДИН раз здесь (off-hot-path, в треде чтобы не
        # блокировать loop) и кладём в чекпоинт — дальше читается из кэша.
        on_channel = False
        try:
            pub = await asyncio.to_thread(get_published_titles, req.lang)
            on_channel = bool(req.topic and pub and not _drop_published_ideas(
                [{"title_original": req.topic}], pub))
        except Exception:
            on_channel = False
        _update_checkpoint(workspace, {
            "script_score": a["score"], "script_ru": a["script_ru"],
            "script_rubric": a.get("rubric"),
            "script_de": script_text, "status": "script_ready", "current_phase": "virality_filter",
            "on_channel": on_channel,
        })
    except Exception as exc:
        logger.error(f"Script draft failed for {task_id}: {exc}")
        _update_checkpoint(workspace, {"status": "failed", "error": str(exc)})
    finally:
        _running_tasks.pop(task_id, None)


async def _resume_video(task_id: str, ws: Path):
    from backend.pipeline.orchestrator import Pipeline, VideoTask
    from backend.pipeline.fcpxml_export import ffprobe_duration
    task = VideoTask.load_checkpoint(ws)
    # load_checkpoint не хранит path-атрибуты — восстановим из файлов на диске,
    # иначе resume с поздней фазы (clips/music/assembly) падает на None-пути.
    # Порядок важен: более поздний файл перетирает ранний для того же атрибута.
    for fname, attr in (("script.txt", "script_path"),
                        ("improved_script.txt", "improved_script_path"),
                        ("viral_script.txt", "improved_script_path"),
                        ("scene_plan.json", "scene_plan_path"),
                        ("scene_plan_aligned.json", "scene_plan_path"),
                        ("voiceover.mp3", "voiceover_path"),
                        ("clip_map.json", "clip_map_path"),
                        ("music.mp3", "music_path")):
        p = ws / fname
        if p.exists():
            setattr(task, attr, str(p))
    if task.voiceover_path:
        try:
            task.voiceover_duration = ffprobe_duration(Path(task.voiceover_path)) or None
        except Exception:
            pass
    try:
        await Pipeline().run(task, skip_completed=True)
        add_to_channel_history(task.lang, task.topic)
    except Exception as exc:
        logger.error(f"Resume failed for {task_id}: {exc}")
        if task.status != "failed":
            task.status = "failed"; task.error = str(exc); task.save_checkpoint()
    finally:
        _running_tasks.pop(task_id, None)


async def _run_improve(task_id: str, ws: Path):
    """Кнопка «Улучшить»: адресное улучшение под судьёй (improve_script сам зовёт
    судью, чинит слабые места, откатывает если балл не вырос) → финальная рубрика."""
    from backend.pipeline.script import improve_script, assess_script
    cp = _read_checkpoint(ws) or {}
    lang = cp.get("lang", "de")
    prev_score = cp.get("script_score")
    vp = ws / "viral_script.txt"
    base = vp.read_text(encoding="utf-8") if vp.exists() else cp.get("script_de", "")
    try:
        improved = await improve_script(base, lang, topic=cp.get("topic"))
        if len(improved) < 0.8 * len(base):
            improved = base
        a = await assess_script(improved, lang)
        # «Улучшить» НЕ должно опускать балл: если пере-оценка дала меньше прежнего —
        # оставляем прежнюю версию (текст + балл + рубрику) без изменений. Судья
        # детерминирован (temp 0), так что это ловит только реально-неудачные правки.
        if isinstance(prev_score, (int, float)) and a["score"] <= prev_score:
            logger.info(f"improve {task_id}: новый балл {a['score']} <= прежнего {prev_score} — оставляю прежнюю версию")
            # updated_at всё равно обновится (видно, что улучшение отработало), но текст/балл прежние
            _update_checkpoint(ws, {"status": "script_ready",
                                    "improve_note": f"не удалось превзойти прежний балл ({prev_score})"})
        else:
            vp.write_text(improved, encoding="utf-8")
            note = (f"улучшено {prev_score}→{a['score']}" if isinstance(prev_score, (int, float))
                    else f"оценено: {a['score']}")
            _update_checkpoint(ws, {
                "script_score": a["score"], "script_ru": a["script_ru"],
                "script_rubric": a.get("rubric"),
                "script_de": improved, "status": "script_ready", "improve_note": note,
            })
    except Exception as exc:
        logger.error(f"Improve failed for {task_id}: {exc}")
        _update_checkpoint(ws, {"status": "script_ready", "error": str(exc)})
    finally:
        _running_tasks.pop(task_id, None)


@app.post("/api/v1/scripts", response_model=VideoResponse, status_code=202, tags=["scripts"])
async def create_script(req: CreateVideoRequest):
    _ensure_free_space()
    """Этап 1 гейта: сгенерировать ТОЛЬКО сценарий (script→improve→virality) + балл + RU."""
    from backend.pipeline.orchestrator import VideoTask
    seed = VideoTask(
        topic=req.topic, lang=req.lang, duration_minutes=req.duration_minutes,
        style=req.style, music_mood=req.music_mood, output_mode=req.output_mode,
        tts_mode=req.tts_mode, visual_mode=_resolve_visual_mode(getattr(req, "visual_mode", None), req.lang),
    )
    task_id = seed.task_id
    workspace = seed.workspace
    _update_checkpoint(workspace, {
        "task_id": task_id, "topic": req.topic, "lang": req.lang,
        "duration_minutes": req.duration_minutes, "style": req.style,
        "music_mood": req.music_mood, "output_mode": req.output_mode, "tts_mode": req.tts_mode,
        "visual_mode": _resolve_visual_mode(getattr(req, "visual_mode", None), req.lang),
        "status": "pending", "current_phase": "", "checkpoint": {},
        "created_at": now_iso(),
    })
    # Тема ушла в работу → помечаем в архиве использованной (для UI-фильтра)
    try:
        mark_topic_used(req.lang, req.topic)
    except Exception as e:
        logger.warning(f"mark_topic_used failed: {e}")
    _running_tasks[task_id] = asyncio.create_task(_run_script_draft(task_id, req, workspace))
    return _checkpoint_to_response(_read_checkpoint(workspace), workspace)


def _clone_draft_to_video(draft_ws: Path, cp: dict, tts_mode: str, visual_mode: str):
    """Клонирует сценарий-черновик в НОВЫЙ video-workspace и возвращает (id, ws).

    Черновик остаётся нетронутым (status script_ready) — из одного сценария можно
    собрать несколько видео (разные visual_mode/tts_mode), сам сценарий не теряется.
    Копируем лёгкие исходники сценария и помечаем script-фазы готовыми, чтобы resume
    не переписывал сценарий заново (LLM-стоимость), а стартовал с озвучки.
    """
    from backend.pipeline.orchestrator import VideoTask
    seed = VideoTask(
        topic=cp.get("topic", ""), lang=cp.get("lang", "de"),
        duration_minutes=cp.get("duration_minutes", 22),
        style=cp.get("style", "documentary"), music_mood=cp.get("music_mood", "auto"),
        output_mode=cp.get("output_mode", "fcpxml"),
        tts_mode=tts_mode, visual_mode=visual_mode,
    )
    new_id, new_ws = seed.task_id, seed.workspace
    for fname in ("script.txt", "improved_script.txt", "viral_script.txt"):
        src = draft_ws / fname
        if src.exists():
            shutil.copy2(src, new_ws / fname)
    _update_checkpoint(new_ws, {
        "task_id": new_id, "topic": cp.get("topic", ""), "lang": cp.get("lang", "de"),
        "duration_minutes": cp.get("duration_minutes", 22), "style": cp.get("style", "documentary"),
        "music_mood": cp.get("music_mood", "auto"), "output_mode": cp.get("output_mode", "fcpxml"),
        "tts_mode": tts_mode, "visual_mode": visual_mode,
        "script_score": cp.get("script_score"), "script_ru": cp.get("script_ru"),
        "script_de": cp.get("script_de"),
        "status": "running", "current_phase": "voiceover",
        "checkpoint": {"script_generation": True, "script_improvement": True, "virality_filter": True},
        "from_draft": draft_ws.name,
        "created_at": now_iso(),
    })
    logger.info(f"approve: склонировал черновик {draft_ws.name} → видео {new_id} (visual={visual_mode}, tts={tts_mode})")
    return new_id, new_ws


@app.post("/api/v1/videos/{task_id}/approve", response_model=VideoResponse, status_code=202, tags=["scripts"])
async def approve_script(task_id: str, req: ApproveScriptRequest = None):
    _ensure_free_space()
    """Этап 2 гейта: одобрить сценарий → собрать видео.
    Сценарий КЛОНИРУЕТСЯ в новое видео — черновик остаётся для повторного использования.
    tts_mode/visual_mode из body переопределяют сохранённое при создании черновика."""
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(ws)
    if not cp or cp.get("status") != "script_ready":
        raise HTTPException(409, "Script not ready for approval")
    tts_mode = (req.tts_mode if req and req.tts_mode else None) or cp.get("tts_mode", "fal")
    # «pexels» в запросе = НЕ задано явно (дефолт UI) → не перетираем черновик.
    # Источник истины: явный non-default запрос → visual_mode черновика → дефолт канала.
    req_vm = req.visual_mode if (req and req.visual_mode and req.visual_mode != "pexels") else None
    visual_mode = req_vm or cp.get("visual_mode") or _resolve_visual_mode(None, cp.get("lang", "de"))
    new_id, new_ws = _clone_draft_to_video(ws, cp, tts_mode, visual_mode)
    _running_tasks[new_id] = asyncio.create_task(_resume_video(new_id, new_ws))
    return _checkpoint_to_response(_read_checkpoint(new_ws), new_ws)


@app.post("/api/v1/scripts/{task_id}/improve", response_model=VideoResponse, status_code=202, tags=["scripts"])
async def improve_script_endpoint(task_id: str):
    """Доп. итерация улучшения сценария + пересчёт балла/перевода."""
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(ws)
    if not cp or cp.get("status") != "script_ready":
        raise HTTPException(409, "Script not ready")
    _update_checkpoint(ws, {"status": "running", "current_phase": "script_improvement"})
    _running_tasks[task_id] = asyncio.create_task(_run_improve(task_id, ws))
    return _checkpoint_to_response(_read_checkpoint(ws), ws)


@app.post("/api/v1/videos/{task_id}/retry", response_model=VideoResponse, status_code=202, tags=["videos"])
async def retry_video(task_id: str):
    _ensure_free_space()
    """Продолжить упавшую/прерванную задачу С ТОГО ЖЕ МЕСТА (skip_completed пропускает
    готовые фазы → пайплайн возобновляется с фазы, где была ошибка)."""
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(ws)
    if not cp:
        raise HTTPException(404, f"Task {task_id} not found")
    bg = _running_tasks.get(task_id)
    if bg and not bg.done():
        raise HTTPException(409, "Task already running")
    _update_checkpoint(ws, {"status": "running", "error": None})
    _running_tasks[task_id] = asyncio.create_task(_resume_video(task_id, ws))
    return _checkpoint_to_response(_read_checkpoint(ws), ws)


# источники для пересборки: лёгкие артефакты ранних фаз (сценарий/озвучка/тайминги)
_REBUILD_KEEP = (
    "script.txt", "improved_script.txt", "viral_script.txt",
    "voiceover.mp3", "scene_plan.json", "scene_plan_aligned.json",
)
_REBUILD_KEEP_FLAGS = (
    "script_generation", "script_improvement", "virality_filter",
    "voiceover", "scene_planning", "alignment",  # порядок = новый пайплайн
)


@app.post("/api/v1/videos/{task_id}/rebuild", response_model=VideoResponse, status_code=202, tags=["videos"])
async def rebuild_video(task_id: str, req: ApproveScriptRequest = None):
    """Пересобрать ГОТОВОЕ видео: сценарий/озвучка/тайминги сохраняются (восстанавливаются
    из zip-а, если медиа уже вычищено), а клипы→музыка→сборка→zip делаются заново —
    с текущими фиксами пайплайна. tts_mode в body позволяет сменить голос при пересборке."""
    import zipfile
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    bg = _running_tasks.get(task_id)
    if bg and not bg.done():
        raise HTTPException(409, "Task already running")

    # re-voice: переозвучить новым голосом + пересчитать тайминги, а сцены/сценарий/
    # картинки переиспользовать. Выкидываем старую озвучку и выравнивание (и НЕ
    # восстанавливаем их из zip), scene_plan и картинки остаются → те же 95 кадров под
    # новый голос. Это и есть основа мульти-язык (одни картинки, переозвучка под язык).
    revoice = bool(req and getattr(req, "revoice", False))
    keep_visuals = bool(req and getattr(req, "keep_visuals", False))
    if keep_visuals:
        revoice = True  # keep_visuals = переозвучка + сохранить картинки/музыку (только re-time)
    keep_files = _REBUILD_KEEP
    if keep_visuals:
        # переозвучка с сохранением визуала: удаляем ТОЛЬКО озвучку, всё остальное
        # (картинки, музыку, clip_map, тайминги) сохраняем и пере-таймим под новый голос.
        keep_files = tuple(f for f in _REBUILD_KEEP if f != "voiceover.mp3")
        (ws / "voiceover.mp3").unlink(missing_ok=True)
    elif revoice:
        keep_files = tuple(f for f in _REBUILD_KEEP if f not in ("voiceover.mp3", "scene_plan_aligned.json"))
        for f in ("voiceover.mp3", "scene_plan_aligned.json"):
            (ws / f).unlink(missing_ok=True)

    # СНАЧАЛА восстановим исходники из zip, ПОТОМ чистим место (и zip-источник
    # под защитой — раньше space-guard удалял его до извлечения озвучки)
    zip_path = ws.parent / f"{ws.name}.zip"
    missing = [f for f in keep_files if not (ws / f).exists()]
    if missing and zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                for f in missing:
                    member = f"{ws.name}/{f}"
                    if member in names:
                        zf.extract(member, ws.parent)
        except Exception as e:
            logger.warning(f"rebuild: извлечение из zip не удалось: {e}")
    # Восстанавливаем картинки (stick_*.png) + sentinel из zip: delivery чистит медиа
    # ПОСЛЕ упаковки, поэтому на пересборке их нет на диске → без этого generate_stick
    # генерировал бы их ЗАНОВО (и деньги, и ДРУГИЕ картинки). С восстановлением —
    # переиспользуются те же оплаченные кадры (важно для re-voice и пересборок).
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for m in zf.namelist():
                    if not m.startswith(ws.name + "/"):
                        continue
                    rel = m[len(ws.name) + 1:]
                    fn = rel.rsplit("/", 1)[-1]
                    if ((fn.startswith("stick_") and fn.endswith(".png"))
                            or fn in ("_style_version.txt", "scene_prompts.json", "clip_map.json", "music.mp3")):
                        if rel and not (ws / rel).exists():
                            zf.extract(m, ws.parent)
        except Exception as e:
            logger.warning(f"rebuild: восстановление картинок из zip не удалось: {e}")
    _ensure_free_space(exclude={zip_path})

    if not any((ws / f).exists() for f in ("viral_script.txt", "improved_script.txt", "script.txt")):
        raise HTTPException(409, "Сценарий не найден ни в workspace, ни в zip — пересборка невозможна, сгенерируй видео заново")

    # ранние фазы остаются готовыми; озвучка/тайминги — только если файлы реально есть
    flags = {k: True for k in _REBUILD_KEEP_FLAGS}
    if keep_visuals:
        # ТОЛЬКО переозвучка; scene_planning+alignment СОХРАНЯЕМ (re-time идёт по готовому
        # clip_map, не по scene_plan). Картинки и музыка не трогаются — только новый голос.
        flags.pop("voiceover", None)
        logger.info(f"rebuild {task_id}: keep_visuals — переозвучка, картинки/музыка сохранены, re-time таймингов")
    elif revoice:
        # переозвучка + пересчёт таймингов; scene_planning СОХРАНЯЕМ → те же сцены →
        # картинки stick_NNN.png (по индексу сцены) совпадают и переиспользуются.
        flags.pop("voiceover", None)
        flags.pop("alignment", None)
        logger.info(f"rebuild {task_id}: re-voice ({(req and req.tts_mode) or 'fal'}) — "
                    f"переозвучка + пересчёт таймингов, сцены/картинки reuse")
    elif not (ws / "voiceover.mp3").exists():
        # озвучка невосстановима → переозвучим ТОТ ЖЕ текст (tts_mode из запроса или из checkpoint)
        flags.pop("voiceover", None)
        flags.pop("alignment", None)
        flags.pop("scene_planning", None)  # scene_plan должен пересчитаться по новой озвучке
        logger.info(f"rebuild {task_id}: voiceover невосстановим — будет переозвучка того же текста")
    # Пересборка ДОЛЖНА применять текущий фикс visual_mode (старый чекпоинт мог хранить
    # буггый "pexels"). Перерезолвим по каналу. Озвучку (дорогую фазу) НЕ трогаем.
    cp = _read_checkpoint(ws) or {}
    visual_mode = _resolve_visual_mode((req.visual_mode if req else None), cp.get("lang", "de"))
    # vi (stick_figure): scene_plan уже doodle (с прошлого билда) → НЕ перепланируем и НЕ
    # переозвучиваем. Клипы переиспользуют готовые PNG (генерация проверяет наличие файла)
    # → пересборка картинок БЕСПЛАТНА, если они уже сделаны по тем же сценам. Только если
    # картинок ещё нет (первый раз / вычищены) — догенерит недостающие.
    cp_updates: dict = {"status": "running", "error": None, "checkpoint": flags,
                        "current_phase": "", "visual_mode": visual_mode, "keep_visuals": keep_visuals}
    if req and req.tts_mode:
        cp_updates["tts_mode"] = req.tts_mode
    _update_checkpoint(ws, cp_updates)
    _running_tasks[task_id] = asyncio.create_task(_resume_video(task_id, ws))
    return _checkpoint_to_response(_read_checkpoint(ws), ws)


# язык-нейтральные артефакты, которые перевод копирует из источника как есть
# (картинки/музыка/тайминги/стиль) — то, ради чего мульти-язык почти бесплатен
def _is_translate_asset(rel: str, fn: str) -> bool:
    return (
        (fn.startswith("stick_") and fn.endswith(".png"))
        or fn in ("clip_map.json", "music.mp3", "_style_version.txt",
                  "scene_prompts.json", "scene_plan.json", "scene_plan_aligned.json",
                  "viral_script.txt", "improved_script.txt", "script.txt")
    )


def _restore_from_zip(ws: Path, predicate) -> int:
    """Извлечь из {ws}.zip файлы, для которых predicate(rel, fn)→True и которых нет
    на диске (delivery чистит медиа после упаковки). Возвращает число извлечённых."""
    import zipfile
    zip_path = ws.parent / f"{ws.name}.zip"
    if not zip_path.exists():
        return 0
    n = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for m in zf.namelist():
                if not m.startswith(ws.name + "/"):
                    continue
                rel = m[len(ws.name) + 1:]
                if not rel or rel.endswith("/"):
                    continue
                fn = rel.rsplit("/", 1)[-1]
                if predicate(rel, fn) and not (ws / rel).exists():
                    zf.extract(m, ws.parent)
                    n += 1
    except Exception as e:
        logger.warning(f"_restore_from_zip({ws.name}): {e}")
    return n


async def _clone_translated_to_video(src_ws: Path, src_cp: dict, req: TranslateVideoRequest):
    """Клонирует ГОТОВОЕ stick_figure-видео в новый workspace целевого языка: те же
    картинки/музыка/тайминги, переведённый сценарий + флаги keep_visuals/is_translation.
    _resume_video дальше переозвучит целевым голосом, пере-таймит ТЕ ЖЕ кадры (retime),
    оставит музыку и переведёт метаданные/превью. Источник не трогаем."""
    from backend.pipeline.orchestrator import VideoTask
    from backend.pipeline.script import translate_script
    src_lang = src_cp.get("lang", "es")
    target_lang = req.target_lang

    # 1. Гарантируем язык-нейтральные артефакты источника (delivery мог их вычистить)
    _restore_from_zip(src_ws, _is_translate_asset)
    if not (src_ws / "clip_map.json").exists():
        raise HTTPException(409, "clip_map.json источника не найден (ни на диске, ни в zip) — нечего переозвучивать")
    src_script = None
    for fn in ("viral_script.txt", "improved_script.txt", "script.txt"):
        p = src_ws / fn
        if p.exists():
            src_script = p.read_text(encoding="utf-8")
            break
    if not src_script:
        raise HTTPException(409, "Сценарий источника не найден — перевод невозможен")

    # 2. Новый workspace целевого языка (duration/стиль/режим — из источника, НЕ дефолт канала)
    seed = VideoTask(
        topic=src_cp.get("topic", ""), lang=target_lang,
        duration_minutes=src_cp.get("duration_minutes", 9),
        style=src_cp.get("style", "documentary"),
        music_mood=src_cp.get("music_mood", "calm"),
        output_mode=src_cp.get("output_mode", "fcpxml"),
        tts_mode=req.tts_mode, visual_mode="stick_figure",
        keep_visuals=True, is_translation=True, voice_id_override=req.voice_id,
    )
    new_id, new_ws = seed.task_id, seed.workspace

    # 3. Копируем язык-нейтральные файлы (картинки/музыка/тайминги/стиль) как есть
    for src in sorted(src_ws.glob("stick_*.png")):
        shutil.copy2(src, new_ws / src.name)
    for fn in ("music.mp3", "clip_map.json", "scene_plan.json",
               "scene_plan_aligned.json", "_style_version.txt", "scene_prompts.json"):
        p = src_ws / fn
        if p.exists():
            shutil.copy2(p, new_ws / fn)

    # 4. КРИТИЧНО: пути в clip_map.json абсолютные на СТАРЫЙ ws → переписать на новый,
    # иначе retime_clip_map пере-кодирует mp4 в чужой папке источника.
    cm_path = new_ws / "clip_map.json"
    try:
        cm = json.loads(cm_path.read_text(encoding="utf-8"))
        for c in cm:
            if c.get("path"):
                c["path"] = str(new_ws / Path(c["path"]).name)
        cm_path.write_text(json.dumps(cm, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"translate: перепись путей clip_map не удалась: {e}")

    # 5. Перевод сценария src→target (дорогую генерацию НЕ повторяем — только перевод)
    translated = await translate_script(src_script, src_lang, target_lang, topic=src_cp.get("topic", ""))
    for fn in ("script.txt", "improved_script.txt", "viral_script.txt"):
        (new_ws / fn).write_text(translated, encoding="utf-8")

    # 6. Checkpoint: keep_visuals+is_translation, ранние фазы готовы (skip), voiceover НЕ
    # ставим → переозвучка. src_metadata/src_lang → _phase_metadata переведёт, не сгенерит.
    _update_checkpoint(new_ws, {
        "task_id": new_id, "topic": src_cp.get("topic", ""), "lang": target_lang,
        "duration_minutes": src_cp.get("duration_minutes", 9),
        "style": src_cp.get("style", "documentary"),
        "music_mood": src_cp.get("music_mood", "calm"),
        "output_mode": src_cp.get("output_mode", "fcpxml"),
        "tts_mode": req.tts_mode, "visual_mode": "stick_figure",
        "keep_visuals": True, "is_translation": True, "voice_id_override": req.voice_id,
        "src_metadata": (src_cp.get("metadata") or {}) if req.translate_metadata else None,
        "src_lang": src_lang,
        # Оценка/RU наследуются от источника (контент тот же, перевод судью не гоняет) —
        # чтобы в библиотеке у переведённого видоса был балл качества и понятный русский.
        "script_score": src_cp.get("script_score"),
        "script_ru": src_cp.get("script_ru"),
        "status": "running", "current_phase": "voiceover",
        "checkpoint": {"script_generation": True, "script_improvement": True,
                       "virality_filter": True, "scene_planning": True, "alignment": True},
        "from_translate": src_ws.name,
        "created_at": now_iso(),
    })
    logger.info(f"translate: {src_ws.name}({src_lang}) → {new_id}({target_lang}), картинки/музыка reuse")
    return new_id, new_ws


@app.post("/api/v1/videos/{task_id}/translate", response_model=VideoResponse, status_code=202, tags=["videos"])
async def translate_video(task_id: str, req: TranslateVideoRequest):
    """Сделать ТУ ЖЕ версию видео на другом языке: картинки/музыка источника
    переиспользуются, переводится сценарий → новая озвучка + пере-тайминг тех же кадров +
    переведённые метаданные/превью. Источник остаётся нетронутым; создаётся новая задача."""
    _ensure_free_space()
    src_ws = _find_workspace_by_task_id(task_id)
    if src_ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(src_ws)
    if not cp:
        raise HTTPException(404, f"Task {task_id} not found")
    if cp.get("visual_mode") != "stick_figure":
        raise HTTPException(409, "Перевод доступен только для мультяшных (stick_figure) видео — переиспользование картинок работает лишь для них")
    if req.target_lang == cp.get("lang"):
        raise HTTPException(409, f"Целевой язык совпадает с языком источника ({cp.get('lang')})")
    new_id, new_ws = await _clone_translated_to_video(src_ws, cp, req)
    _running_tasks[new_id] = asyncio.create_task(_resume_video(new_id, new_ws))
    return _checkpoint_to_response(_read_checkpoint(new_ws), new_ws)


@app.post("/api/v1/videos/translate-upload", response_model=VideoResponse, status_code=202, tags=["videos"])
async def translate_upload(
    file: UploadFile = File(...),
    target_lang: str = Form(...),
    voice_id: str = Form(""),
    tts_mode: str = Form("fal"),
    translate_metadata: bool = Form(True),
):
    """Перевод из ЗАГРУЖЕННОГО zip: клиент заливает готовый stick_figure-видос (напр. es),
    мы восстанавливаем его картинки/тайминги ИЗ зипа и делаем версию на target_lang
    (переозвучка + retime ТЕХ ЖЕ кадров) — БЕЗ перегенерации картинок. Спасает, когда
    серверный zip уже вычищен, а у клиента он есть. Может занять ~минуту (перевод)."""
    import zipfile, uuid as _uuid
    _ensure_free_space()
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    tmp_zip = OUTPUT_DIR / f"_upload_{_uuid.uuid4().hex[:8]}.zip"
    try:
        tmp_zip.write_bytes(data)
        with zipfile.ZipFile(tmp_zip) as zf:
            # workspace = папка, содержащая clip_map.json. Надёжно мимо Mac-мусора
            # (__MACOSX/.DS_Store при пере-сжатии на Маке), любой вложенности.
            names = [n for n in zf.namelist() if not n.startswith("__MACOSX")]
            cm = (next((n for n in names if n.endswith("/clip_map.json")), None)
                  or next((n for n in names if n.rsplit("/", 1)[-1] == "clip_map.json"), None))
            if not cm:
                raise HTTPException(400, "В зипе нет clip_map.json — это не видос фабрики (или зип повреждён)")
            ws_rel = cm.rsplit("clip_map.json", 1)[0].rstrip("/")
            for n in zf.namelist():           # извлекаем всё КРОМЕ __MACOSX-мусора
                if not n.startswith("__MACOSX"):
                    zf.extract(n, OUTPUT_DIR)
        es_ws = (OUTPUT_DIR / ws_rel) if ws_rel else OUTPUT_DIR
        es_ws_name = es_ws.name
        final_zip = OUTPUT_DIR / f"{es_ws_name}.zip"
        if final_zip.exists():
            tmp_zip.unlink(missing_ok=True)
        else:
            tmp_zip.replace(final_zip)
    except HTTPException:
        tmp_zip.unlink(missing_ok=True)
        raise
    except Exception as e:
        tmp_zip.unlink(missing_ok=True)
        raise HTTPException(400, f"Не удалось распаковать zip: {e}")

    # checkpoint.json ИСКЛЮЧЁН из зипа (delivery ZIP_EXCLUDE) → восстанавливаем нужное
    # из содержимого: lang (по metadata_{lang}.json / имени папки), metadata, topic.
    es_cp = _read_checkpoint(es_ws) or {}
    if not es_cp.get("lang"):
        src_lang = None
        for mf in sorted(es_ws.glob("metadata_*.json")):
            src_lang = mf.stem.split("_", 1)[-1]
            break
        if not src_lang:
            parts = es_ws_name.rsplit("_", 2)
            src_lang = parts[1] if (len(parts) == 3 and len(parts[1]) <= 3) else "es"
        meta = {}
        mf = es_ws / f"metadata_{src_lang}.json"
        if mf.exists():
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        topic = es_ws_name.rsplit("_", 2)[0].replace("_", " ")
        if meta.get("titles"):
            topic = str(meta["titles"][0])
        es_cp = {
            "lang": src_lang, "topic": topic, "visual_mode": "stick_figure",
            "duration_minutes": 9, "style": "documentary", "music_mood": "calm",
            "output_mode": "fcpxml", "metadata": meta,
        }
    if not any(es_ws.glob("stick_*.png")):
        raise HTTPException(409, "В зипе нет картинок stick_*.png — нечего переиспользовать")
    if not (es_ws / "clip_map.json").exists():
        raise HTTPException(409, "В зипе нет clip_map.json — нечего переиспользовать")
    if target_lang == es_cp.get("lang"):
        raise HTTPException(409, f"Целевой язык совпадает с языком источника ({es_cp.get('lang')})")
    req = TranslateVideoRequest(
        target_lang=target_lang, voice_id=(voice_id or None),
        tts_mode=tts_mode, translate_metadata=bool(translate_metadata))
    new_id, new_ws = await _clone_translated_to_video(es_ws, es_cp, req)
    _running_tasks[new_id] = asyncio.create_task(_resume_video(new_id, new_ws))
    logger.info(f"translate-upload: {es_ws_name}({es_cp.get('lang')}) → {new_id}({target_lang}) из загруженного зипа")
    return _checkpoint_to_response(_read_checkpoint(new_ws), new_ws)


def _configured_langs() -> list[str]:
    """Языки из channels.yaml — чтобы factory_reset/история чистились для ВСЕХ
    каналов (включая vi и будущие), а не по хардкод-списку de/es/en."""
    try:
        return list(load_yaml("channels").get("channels", {}).keys())
    except Exception:
        return ["de", "es", "en", "vi"]


@app.delete("/api/v1/factory/reset", status_code=204, tags=["system"])
async def factory_reset(scope: str = "all", keep_scripts: bool = True):
    """Очистка данных ПО ВКЛАДКАМ — сброс одной вкладки не трогает другие. scope:
      all     — всё (видео + черновики по keep_scripts + история каналов) — старое поведение
      queue   — только активные/упавшие задачи (НЕ библиотека, НЕ черновики)
      library — только готовые видео (completed) + их zip
      drafts  — только черновики-сценарии (script_ready)
      topics  — только архив найденных тем (topics_<lang>.json)"""
    scope = (scope or "all").lower()

    # topics — отдельный стор, workspace-папки не трогаем
    if scope == "topics":
        for lang in _configured_langs():
            tf = DATA_DIR / f"topics_{lang}.json"
            if tf.exists():
                try:
                    tf.unlink()
                except Exception as e:
                    logger.warning(f"factory_reset topics {lang}: {e}")
        logger.info("factory_reset: архив тем очищен")
        return

    def _match(status: str) -> bool:
        if scope == "all":
            return not (keep_scripts and status == "script_ready")
        if scope == "queue":
            return status not in ("completed", "script_ready")
        if scope == "library":
            return status == "completed"
        if scope == "drafts":
            return status == "script_ready"
        return False

    # Отменить запущенные задачи (только для scope, который их затрагивает)
    if scope in ("queue", "all"):
        for task_id, bg_task in list(_running_tasks.items()):
            if bg_task and not bg_task.done():
                bg_task.cancel()
        _running_tasks.clear()

    if OUTPUT_DIR.exists():
        for item in list(OUTPUT_DIR.iterdir()):
            try:
                if item.is_dir():
                    cp = _read_checkpoint(item)
                    status = (cp or {}).get("status", "")
                    if _match(status):
                        shutil.rmtree(item)
                        zp = item.parent / f"{item.name}.zip"
                        if zp.exists():
                            zp.unlink()
                elif item.suffix == ".zip":
                    # сиротский zip (папка уже удалена) — чистим только при all/library
                    if scope in ("all", "library"):
                        item.unlink()
            except Exception as e:
                logger.warning(f"factory_reset: не удалось удалить {item.name}: {e}")

    # история каналов — только при полном сбросе
    if scope == "all":
        for lang in _configured_langs():
            hf = DATA_DIR / f"history_{lang}.json"
            if hf.exists():
                try:
                    hf.unlink()
                except Exception as e:
                    logger.warning(f"factory_reset: история {lang} не удалена: {e}")

    logger.info(f"factory_reset: scope={scope} выполнен")


@app.get("/api/v1/videos", response_model=list[VideoResponse], tags=["videos"])
async def list_videos():
    results = []
    if not OUTPUT_DIR.exists():
        return results
    for ws in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not ws.is_dir():
            continue
        cp = _read_checkpoint(ws)
        if cp:
            results.append(_checkpoint_to_response(cp, ws))
    # Пометить черновики, чья тема УЖЕ собрана в готовое видео (есть в Библиотеке) —
    # чтобы клиент не собрал один и тот же сценарий дважды.
    def _tkey(r):
        return ((r.lang or ""), re.sub(r"\s+", " ", (r.topic or "").strip().lower()))
    built = {_tkey(r) for r in results if r.status == "completed"}
    if built:
        for r in results:
            if r.status == "script_ready" and _tkey(r) in built:
                r.already_built = True
    return results


@app.get("/api/v1/videos/{task_id}", response_model=VideoResponse, tags=["videos"])
async def get_video(task_id: str):
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(ws)
    return _checkpoint_to_response(cp, ws)


@app.get("/api/v1/videos/{task_id}/download", tags=["videos"])
async def download_video(task_id: str):
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    cp = _read_checkpoint(ws)
    if not cp or cp.get("status") != "completed":
        raise HTTPException(409, "Video not ready")
    topic_safe = cp.get("topic", task_id)[:40].replace(" ", "_").replace("/", "_")
    lang = cp.get("lang", "xx")
    # fcpxml-режим: отдаём zip DaVinci-проекта (zip лежит рядом с workspace)
    zip_path = ws.parent / f"{ws.name}.zip"
    if zip_path.exists():
        # Помечаем zip как СКАЧАННЫЙ. space-guard теперь удаляет ТОЛЬКО скачанные
        # zip — не скачанное видео (работа клиента, которую он ещё не забрал) НИКОГДА
        # не удаляется автоматически. Раньше удалялись старейшие подряд → терялись
        # не скачанные видео (клиент справедливо был в ярости).
        try:
            Path(str(zip_path) + ".downloaded").touch()
        except Exception:
            pass
        return FileResponse(str(zip_path), media_type="application/zip",
                            filename=f"{topic_safe}_{lang}.zip")
    mp4_files = list(ws.glob("final_*.mp4"))
    if mp4_files:
        return FileResponse(str(mp4_files[0]), media_type="video/mp4",
                            filename=f"{topic_safe}_{lang}.mp4")
    raise HTTPException(404, "Video file not found")


@app.delete("/api/v1/videos/{task_id}", status_code=204, tags=["videos"])
async def cancel_video(task_id: str):
    """Удалить видео: отменяет запущенную задачу И стирает workspace + zip, чтобы
    освободить место (дедуп тем теперь идёт по YouTube-каналу, локальная копия не нужна).
    Черновики-сценарии (script_ready) НЕ трогаем — их клиент хранит отдельно."""
    ws = _find_workspace_by_task_id(task_id)
    if ws is None:
        raise HTTPException(404, f"Task {task_id} not found")
    bg_task = _running_tasks.get(task_id)
    if bg_task and not bg_task.done():
        bg_task.cancel()
        try:
            await bg_task
        except (asyncio.CancelledError, Exception):
            pass
        _running_tasks.pop(task_id, None)

    cp = _read_checkpoint(ws)
    if cp and cp.get("status") == "script_ready":
        # черновик сценария — не удаляем файлы, просто помечаем (защита архива сценариев)
        _update_checkpoint(ws, {"status": "cancelled"})
        return
    # полное удаление: workspace-папка + zip → освобождаем место на томе
    zip_path = ws.parent / f"{ws.name}.zip"
    freed = 0
    try:
        for p in ws.rglob("*"):
            if p.is_file():
                freed += p.stat().st_size
        shutil.rmtree(ws, ignore_errors=True)
    except Exception as e:
        logger.warning(f"delete {task_id}: rmtree {ws.name}: {e}")
    try:
        if zip_path.exists():
            freed += zip_path.stat().st_size
            zip_path.unlink()
    except Exception as e:
        logger.warning(f"delete {task_id}: zip: {e}")
    logger.info(f"delete {task_id}: освобождено {freed/1024/1024:.0f} MB ({ws.name})")


# ── WebSocket ──

@app.websocket("/api/v1/ws/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    ws_dir = _find_workspace_by_task_id(task_id)
    if ws_dir is None:
        await websocket.send_json({"error": f"Task {task_id} not found"})
        await websocket.close()
        return
    try:
        last_hash = None
        misses = 0
        while True:
            cp = await asyncio.to_thread(_read_checkpoint, ws_dir)  # чтение тома — не в loop
            if cp:
                misses = 0
                response = _checkpoint_to_response(cp, ws_dir)
                payload = response.model_dump()
                payload_hash = json.dumps(payload, sort_keys=True)
                if payload_hash != last_hash:
                    await websocket.send_json(payload)
                    last_hash = payload_hash
                if cp.get("status") in ("completed", "failed", "cancelled"):
                    break
            else:
                # транзиентная нечитаемость (запись в полёте) не должна рвать прогресс;
                # сдаёмся только если нечитаемо ~10с подряд
                misses += 1
                if misses >= 20:
                    await websocket.send_json({"error": "Checkpoint not readable"})
                    break
            await asyncio.sleep(2)  # WS — основной канал; 2с снижает нагрузку на loop
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"WebSocket error for {task_id}: {exc}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass






mount_static(app)
