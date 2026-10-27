"""
Main pipeline orchestrator.
Coordinates all phases of video generation:
  1. Script generation
  2. Script improvement (3 iterations)
  3. Virality filter
  4. TTS voiceover  ← real duration known after this
  5. Scene planning (uses real voiceover duration)
  6. Alignment (word-level timing)
  7. Clip download + Music (parallel)
  8. Video assembly (FFmpeg or FCPXML)
  9. Metadata + Delivery
"""

import asyncio
import json
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from backend.config import OUTPUT_DIR, DATA_DIR, PROJECT_ROOT, now_iso, get_channel_config

logger = logging.getLogger(__name__)


def _chapters_from_aligned_plan(workspace: Path, max_chapters: int = 10) -> list[dict]:
    """Реальные YouTube-главы из aligned scene plan: title-сцены и их тайминги.

    LLM раньше выдумывал таймстампы для description («0:15…3:00, Weitere
    folgen») — они уезжали в YouTube как ложные главы. Здесь только реальные
    времена; первая глава всегда 0:00 (требование YouTube).
    """
    plan_path = workspace / "scene_plan_aligned.json"
    if not plan_path.exists():
        return []
    try:
        scenes = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"chapters: scene_plan_aligned не прочитан ({e})")
        return []
    if not isinstance(scenes, list):
        return []

    def _fmt(sec: float) -> str:
        sec = int(sec)
        return f"{sec // 60}:{sec % 60:02d}"

    chapters = [{"time": "0:00", "hint": "Hook"}]
    last_sec = 0.0
    for s in scenes:
        if s.get("visual_type") != "remotion_title":
            continue
        start = float(s.get("start") or 0)
        hint = (s.get("remotion_data") or {}).get("title", "")
        # главы короче 10с YouTube не принимает; пустые ярлыки бесполезны
        if start - last_sec < 10 or not hint:
            continue
        chapters.append({"time": _fmt(start), "hint": hint})
        last_sec = start
        if len(chapters) >= max_chapters:
            break
    return chapters if len(chapters) >= 3 else []


@dataclass
class VideoTask:
    """Represents a single video generation task."""
    topic: str
    lang: str  # de, es, en
    duration_minutes: int = 22
    style: str = "documentary"  # documentary, cinematic, clean
    music_mood: str = "auto"  # auto, dramatic, calm, dark, uplifting
    output_mode: str = "rendered"  # "rendered" (FFmpeg mp4) | "fcpxml" (DaVinci timeline)
    tts_mode: str = "fal"  # "fal" (бренд-голос, платно ~$2/видео) | "free" (Edge, для тестов)
    visual_mode: str = "pexels"  # "pexels" (сток-клипы) | "stick_figure" (AI картинки)
    keep_visuals: bool = False  # переозвучка: сохранить готовые картинки+музыку, только пере-таймить
    voice_id_override: Optional[str] = None  # мульти-язык: голос целевого языка поверх voices.yaml
    is_translation: bool = False  # клон-перевод на др. язык: метаданные/превью переводятся, не генерятся
    source_transcript: Optional[str] = None  # транскрипт-референс: оригинальный сценарий по его структуре+фактам

    # Internal state
    task_id: str = ""
    workspace: Path = None
    status: str = "pending"  # pending, running, paused, completed, failed
    current_phase: str = ""
    phase_detail: str = ""   # под-шаг внутри фазы («Озвучка: чанк 3/4») — для живого прогресса
    error: str = ""
    
    # Phase outputs
    script_path: Optional[str] = None
    improved_script_path: Optional[str] = None
    voiceover_path: Optional[str] = None
    voiceover_duration: Optional[float] = None
    scene_plan_path: Optional[str] = None
    clip_map_path: Optional[str] = None
    music_path: Optional[str] = None
    final_video_path: Optional[str] = None
    metadata_path: Optional[str] = None
    gdrive_url: Optional[str] = None
    
    # Checkpoint tracking
    checkpoint: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.task_id:
            import uuid
            self.task_id = str(uuid.uuid4())[:8]
        if self.workspace is None:
            import re
            # Имя папки должно быть URL/FS-безопасным: спецсимволы (?, /, &, % …) ломают
            # разбор file:// путей в DaVinci → Media Offline. \w (UNICODE) сохраняет
            # вьетнамские буквы, выкидывает «?» и прочее. См. open-davinci.command.
            safe_topic = self.topic[:50].strip().replace(" ", "_")
            safe_topic = re.sub(r"[^\w\-]", "", safe_topic, flags=re.UNICODE).lower() or "video"
            self.workspace = OUTPUT_DIR / f"{safe_topic}_{self.lang}_{self.task_id}"
        self.workspace = Path(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
    
    def save_checkpoint(self):
        """Save progress to checkpoint file.

        MERGE, а не перезапись: другие фазы дописывают в checkpoint.json свои ключи
        (metadata, delivery) и API — created_at/style/music_mood. Полная перезапись
        их стирала → сайт терял титулы и ссылку на скачивание.
        Запись атомарная (temp+rename), чтобы WS-читатель не словил битый JSON.
        """
        cp_path = self.workspace / "checkpoint.json"
        data = {}
        if cp_path.exists():
            try:
                with open(cp_path) as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data.update({
            "task_id": self.task_id,
            "topic": self.topic,
            "lang": self.lang,
            "duration_minutes": self.duration_minutes,
            "output_mode": self.output_mode,
            "tts_mode": self.tts_mode,
            "visual_mode": self.visual_mode,
            "keep_visuals": self.keep_visuals,
            "voice_id_override": self.voice_id_override,
            "is_translation": self.is_translation,
            "source_transcript": self.source_transcript,
            "status": self.status,
            "current_phase": self.current_phase,
            "phase_detail": self.phase_detail,
            "error": self.error if self.error else None,
            "checkpoint": self.checkpoint,
            "updated_at": now_iso(),
        })
        tmp = cp_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(cp_path)

    def touch(self, detail: str):
        """Обновить под-шаг текущей фазы + updated_at (живой прогресс внутри длинной
        фазы: озвучка/клипы), чтобы было видно что процесс не завис."""
        self.phase_detail = detail
        self.save_checkpoint()

    @classmethod
    def load_checkpoint(cls, workspace: Path) -> Optional["VideoTask"]:
        """Resume a task from checkpoint."""
        cp_path = workspace / "checkpoint.json"
        if not cp_path.exists():
            return None
        with open(cp_path) as f:
            data = json.load(f)
        task = cls(
            topic=data["topic"],
            lang=data["lang"],
            duration_minutes=data.get("duration_minutes", 22),
            output_mode=data.get("output_mode", "rendered"),
            tts_mode=data.get("tts_mode", "fal"),
            visual_mode=data.get("visual_mode", "pexels"),
            keep_visuals=data.get("keep_visuals", False),
            voice_id_override=data.get("voice_id_override"),
            is_translation=data.get("is_translation", False),
            source_transcript=data.get("source_transcript"),
            task_id=data["task_id"],
            workspace=workspace,
        )
        task.status = data.get("status", "paused")
        task.checkpoint = data.get("checkpoint", {})
        return task


class Pipeline:
    """
    Main video generation pipeline.
    
    Usage:
        pipeline = Pipeline()
        task = VideoTask(topic="How Wirecard Fooled Germany", lang="de")
        await pipeline.run(task)
    """
    
    def __init__(self):
        self.phases = [
            ("script_generation", self._phase_script),
            ("script_improvement", self._phase_improve),
            ("virality_filter", self._phase_virality),
            ("voiceover", self._phase_tts),            # ← TTS first: real duration для scene plan
            ("scene_planning", self._phase_scenes),    # ← после TTS: планируем по реальной длине
            ("alignment", self._phase_alignment),      # ★ word-level realign по голосу
            ("clip_download", self._phase_clips),      # ← параллельно с music (asyncio.gather)
            ("music", self._phase_music),
            ("assembly", self._phase_assembly),
            ("metadata", self._phase_metadata),
            ("delivery", self._phase_delivery),
        ]

    async def _run_phase_task(self, task: VideoTask, name: str, fn) -> None:
        """Запустить фазу и отметить в checkpoint. Используется для параллельного запуска."""
        await fn(task)
        task.checkpoint[name] = True
        task.checkpoint[f"{name}_at"] = now_iso()
        task.save_checkpoint()

    async def run(self, task: VideoTask, skip_completed: bool = True, stop_after: str = None) -> VideoTask:
        """Run the pipeline. stop_after: пауза после этой фазы (для гейта одобрения сценария)."""
        task.status = "running"
        total = len(self.phases)
        _parallel_done: set[str] = set()  # фазы, уже обработанные в параллельном блоке

        for i, (phase_name, phase_fn) in enumerate(self.phases, 1):
            # Пропустить фазы, уже обработанные параллельно
            if phase_name in _parallel_done:
                continue

            if skip_completed and task.checkpoint.get(phase_name):
                logger.info(f"[{i}/{total}] Skipping {phase_name} (already done)")
                continue

            task.current_phase = phase_name
            task.phase_detail = ""
            task.save_checkpoint()
            logger.info(f"[{i}/{total}] Starting {phase_name}...")

            # ── Параллельный блок: clip_download + music ────────────────────
            if phase_name == "clip_download":
                music_fn = next((fn for n, fn in self.phases if n == "music"), None)
                if music_fn and not (skip_completed and task.checkpoint.get("music")):
                    _parallel_done.add("music")
                    task.current_phase = "clip_download"
                    task.phase_detail = "клипы + музыка параллельно"
                    task.save_checkpoint()
                    logger.info(f"[{i}/{total}] Starting clip_download + music (parallel)...")

                    results = await asyncio.gather(
                        self._run_phase_task(task, "clip_download", phase_fn),
                        self._run_phase_task(task, "music", music_fn),
                        return_exceptions=True,
                    )
                    clips_result, music_result = results

                    if isinstance(music_result, Exception):
                        # Музыка некритична — продолжаем без неё
                        logger.warning(f"music failed (non-critical, видео без музыки): {music_result}")
                    if isinstance(clips_result, Exception):
                        task.status = "failed"
                        task.error = f"clip_download: {clips_result}"
                        task.save_checkpoint()
                        logger.error(f"[{i}/{total}] Failed at clip_download: {clips_result}")
                        raise clips_result

                    logger.info(f"[{i}/{total}] Completed clip_download + music (parallel)")
                    continue
            # ────────────────────────────────────────────────────────────────

            try:
                await phase_fn(task)
                task.checkpoint[phase_name] = True
                task.checkpoint[f"{phase_name}_at"] = now_iso()
                task.save_checkpoint()
                logger.info(f"[{i}/{total}] Completed {phase_name}")
            except Exception as e:
                task.status = "failed"
                task.error = f"{phase_name}: {str(e)}"
                task.save_checkpoint()
                logger.error(f"[{i}/{total}] Failed at {phase_name}: {e}")
                raise

            if stop_after and phase_name == stop_after:
                # пауза на гейте. Статус "scripting" (транзиентный) — НЕ script_ready:
                # балл/перевод считает _run_script_draft ПОСЛЕ, и он выставит script_ready,
                # чтобы фронт не показал ревью с пустым баллом/переводом.
                task.status = "scripting"
                task.save_checkpoint()
                logger.info(f"[{i}/{total}] Paused after {phase_name} (scripting → assess)")
                return task

        task.status = "completed"
        task.current_phase = "done"
        task.save_checkpoint()
        return task
    
    async def _phase_script(self, task: VideoTask):
        """Phase 1: Generate script from topic."""
        from backend.pipeline.script import generate_script
        src_tr = None
        if task.source_transcript and task.source_transcript.strip():
            # референс-видос как шаблон: структура + реальные факты, оригинальный текст
            src_tr = [{"title": task.topic, "transcript": task.source_transcript}]
        script_text = await generate_script(
            topic=task.topic,
            lang=task.lang,
            duration_minutes=task.duration_minutes,
            source_transcripts=src_tr,
        )
        path = task.workspace / "script.txt"
        path.write_text(script_text, encoding="utf-8")
        task.script_path = str(path)
    
    async def _phase_improve(self, task: VideoTask):
        """Phase 2: Improve script quality (3 iterations)."""
        from backend.pipeline.script import improve_script
        script_text = (task.workspace / "script.txt").read_text(encoding="utf-8")
        improved = await improve_script(
            script=script_text,
            lang=task.lang,
            topic=task.topic,
        )
        # Защита от усадки: improve полирует, а не режет (0.97 чтобы две фазы не
        # перемножали потери: было 0.9×0.9=0.81 → теряли ~19% длины)
        if len(improved) < 0.97 * len(script_text):
            logger.warning(f"improve укоротил {len(script_text)}→{len(improved)} симв — оставляю длинный")
            improved = script_text
        path = task.workspace / "improved_script.txt"
        path.write_text(improved, encoding="utf-8")
        task.improved_script_path = str(path)
    
    async def _phase_virality(self, task: VideoTask):
        """Phase 2.5: Apply virality filter for maximum retention."""
        from backend.pipeline.virality import apply_virality_filter
        script_path = task.improved_script_path or task.script_path
        script_text = Path(script_path).read_text(encoding="utf-8")
        viral_script = await apply_virality_filter(
            script=script_text,
            lang=task.lang,
        )
        # Защита от усадки: virality-фильтр не режет длину (0.97, см. improve)
        if len(viral_script) < 0.97 * len(script_text):
            logger.warning(f"virality укоротил {len(script_text)}→{len(viral_script)} симв — оставляю длинный")
            viral_script = script_text
        # Страховка ПОСЛЕ guard: если ремарочный хвост (ABSPANN/EPILOG…) дожил
        # досюда, режем перед записью — иначе TTS его озвучит, а scene planning
        # построит по нему 5 минут чёрных титров в конце видео.
        from backend.pipeline.script import strip_director_tail
        viral_script = strip_director_tail(viral_script)
        path = task.workspace / "viral_script.txt"
        path.write_text(viral_script, encoding="utf-8")
        task.improved_script_path = str(path)
    
    async def _phase_tts(self, task: VideoTask):
        """Phase 3: Generate voiceover from script."""
        from backend.pipeline.tts import generate_voiceover
        script_path = task.improved_script_path or task.script_path
        script_text = Path(script_path).read_text(encoding="utf-8")
        audio_path, duration = await generate_voiceover(
            text=script_text,
            lang=task.lang,
            output_dir=task.workspace,
            progress_cb=task.touch,
            tts_mode=task.tts_mode,
            voice_id_override=task.voice_id_override,
        )
        task.voiceover_path = str(audio_path)
        task.voiceover_duration = duration
        # Гард минимальной длины: видео <8 мин теряет mid-roll рекламу. Если голос
        # заметно короче целевого (скрипт вышел коротким) — предупреждаем в лог,
        # но прогон не валим (клиент решает, пересобрать ли с более длинным скриптом).
        floor = task.duration_minutes * 60 * 0.85
        if duration and duration < floor:
            logger.warning(
                f"voiceover {duration:.0f}s < минимума {floor:.0f}s "
                f"(цель {task.duration_minutes} мин) — скрипт коротковат, видео может "
                f"не дотянуть до 8 мин (mid-roll реклама)")

    async def _phase_scenes(self, task: VideoTask):
        """Phase 5 (after TTS): Plan scenes with real voiceover duration."""
        from backend.pipeline.clips import plan_scenes
        script_path = task.improved_script_path or task.script_path
        script_text = Path(script_path).read_text(encoding="utf-8")
        # После TTS voiceover_duration — реальная длина. Фолбэк на оценку только при resume без голоса.
        estimated_duration = task.voiceover_duration or float(task.duration_minutes * 60)
        scene_plan = await plan_scenes(
            script=script_text,
            topic=task.topic,
            lang=task.lang,
            total_duration=estimated_duration,
        )
        # Цельно-мультяшный канал (vi/Ngẫm) = 100% Seedream-генерация: форсим doodle
        # на ВСЕ сцены, включая data-инфографику (НИКАКИХ Remotion-карточек и стока),
        # чтобы видеоряд был сплошным мультом как у референса. de/es (pexels) — мимо.
        if task.visual_mode == "stick_figure":
            for s in scene_plan:
                s["visual_type"] = "doodle"
                s.pop("medium", None)
                s.pop("remotion_data", None)
            logger.info(f"stick_figure: форс doodle на ВСЕ {len(scene_plan)} сцен (без Remotion/стока)")
        path = task.workspace / "scene_plan.json"
        with open(path, "w") as f:
            json.dump(scene_plan, f, indent=2, ensure_ascii=False)
        task.scene_plan_path = str(path)
    
    async def _phase_alignment(self, task: VideoTask):
        """Phase 4.5: realign scene_plan timings using Deepgram word-level timestamps.

        Initial scene_plan was generated from TEXT (LLM guessed timings).
        After TTS we know the REAL timing of each word in the voiceover.
        This phase replaces predicted start/end with actual ones.
        """
        from backend.pipeline.align_scenes import realign_scene_plan
        aligned_path = await realign_scene_plan(
            voice_path=Path(task.voiceover_path),
            scene_plan_path=Path(task.scene_plan_path),
            lang=task.lang,
        )
        task.scene_plan_path = str(aligned_path)
        # Гард покрытия: видеоряд обязан тянуться на всю длину голоса. Если alignment
        # всё же схлопнул сцены в начало — детерминированно растягиваем тайминги в
        # [0..voice] (без LLM). Иначе в DaVinci будет чёрный хвост на полвидео.
        voice_dur = float(task.voiceover_duration or 0.0)
        if voice_dur > 0:
            try:
                plan = json.loads(Path(aligned_path).read_text(encoding="utf-8"))
                last_end = max((float(s.get("end", 0.0)) for s in plan if "end" in s), default=0.0)
                if last_end and last_end < voice_dur * 0.9:
                    factor = voice_dur / last_end
                    logger.warning(
                        f"coverage: scene_plan кончается на {last_end:.0f}s при голосе "
                        f"{voice_dur:.0f}s — растягиваю тайминги x{factor:.2f} на всю длину")
                    for s in plan:
                        if "start" in s:
                            s["start"] = round(float(s["start"]) * factor, 3)
                        if "end" in s:
                            s["end"] = round(float(s["end"]) * factor, 3)
                    Path(aligned_path).write_text(
                        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
                else:
                    logger.info(f"coverage: scene_plan end={last_end:.0f}s voice={voice_dur:.0f}s OK")
            except Exception as e:
                logger.warning(f"coverage guard failed ({e}) — пропускаю")

    async def _phase_clips(self, task: VideoTask):
        """Phase 5: видеоряд. ДВА РАЗДЕЛЁННЫХ пайплайна по каналу:
        - stick_figure (vi/Ngẫm) → generate_stick_images_from_scene_plan: КАЖДАЯ сцена =
          Seedream-картинка, НИКАКОГО стока/Pexels/Remotion (функция их не импортирует).
        - pexels (de/es) → download_clips: сток + реальные фото + Remotion + doodle (микс)."""
        # ПЕРЕОЗВУЧКА С СОХРАНЕНИЕМ КАРТИНОК: берём готовый clip_map, масштабируем тайминги
        # под новую длину голоса и пере-кодируем ТЕ ЖЕ картинки в mp4 — никакой Seedream,
        # никакой перепланировки. Картинки и музыка остаются, меняется только голос+тайминги.
        cm_path = task.workspace / "clip_map.json"
        if task.keep_visuals and task.visual_mode == "stick_figure" and cm_path.exists():
            from backend.pipeline.stick_figure import retime_clip_map
            with open(cm_path) as f:
                old_cm = json.load(f)
            clip_map = await retime_clip_map(
                task.workspace, old_cm,
                new_voice_dur=task.voiceover_duration or 0.0, progress_cb=task.touch,
            )
            with open(cm_path, "w") as f:
                json.dump(clip_map, f, indent=2, ensure_ascii=False)
            task.clip_map_path = str(cm_path)
            return
        with open(task.scene_plan_path) as f:
            scene_plan = json.load(f)
        if task.visual_mode == "stick_figure":
            from backend.pipeline.stick_figure import generate_stick_images_from_scene_plan
            # output_dir = КОРЕНЬ workspace (рядом с project.fcpxml), а не clips/ —
            # тогда DaVinci находит картинки при ручном импорте XML, как озвучку/музыку.
            clip_map = await generate_stick_images_from_scene_plan(
                scene_plan, topic=task.topic, output_dir=task.workspace,
                voiceover_duration=task.voiceover_duration, progress_cb=task.touch,
            )
        else:
            from backend.pipeline.clips import download_clips
            clip_map = await download_clips(
                scene_plan=scene_plan,
                output_dir=task.workspace / "clips",
                progress_cb=task.touch,
                topic=task.topic,
            )
        if not clip_map:
            raise RuntimeError(
                "Не удалось получить ни одного клипа для видео. Проверь ключи "
                "стока (PEXELS_API_KEY / PIXABAY_API_KEY) и FALAPI (картинка-фолбэк)."
            )
        path = task.workspace / "clip_map.json"
        with open(path, "w") as f:
            json.dump(clip_map, f, indent=2, ensure_ascii=False)
        task.clip_map_path = str(path)
    
    async def _phase_music(self, task: VideoTask):
        """Phase 6: фоновая дорожка из house-пула на всю длину голоса — рандом-микс
        с кроссфейдами. Пул фильтруется по настроению канала (channels.yaml music_mood):
        de=документальные/тёмные, vi=спокойные/рефлексивные."""
        # Переозвучка с сохранением визуала: музыку НЕ пересобираем (клиент: «музыка
        # офигенная»), оставляем существующую дорожку как есть.
        existing_music = task.workspace / "music.mp3"
        if task.keep_visuals and existing_music.exists() and existing_music.stat().st_size > 1000:
            # Перевод/переозвучка может дать голос ДЛИННЕЕ исходной музыки → хвост видео
            # без музыки. Если музыка короче голоса — зацикливаем ТУ ЖЕ дорожку на полную
            # длину (та же музыка, просто повторяется). Короче-или-равно голосу — оставляем.
            try:
                from backend.pipeline.fcpxml_export import ffprobe_duration
                import subprocess
                voice_dur = float(task.voiceover_duration or 0.0)
                music_dur = float(ffprobe_duration(existing_music) or 0.0)
                if voice_dur > 0 and music_dur > 0 and music_dur < voice_dur - 2:
                    looped = task.workspace / "music_looped.mp3"
                    subprocess.run(
                        ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(existing_music),
                         "-t", f"{voice_dur:.2f}", "-c:a", "libmp3lame", "-q:a", "4",
                         str(looped)],
                        capture_output=True, check=True)
                    looped.replace(existing_music)
                    logger.info(f"music: keep_visuals → зациклил музыку {music_dur:.0f}s→{voice_dur:.0f}s под новый голос")
                else:
                    logger.info("music: keep_visuals → оставляю существующую music.mp3")
            except Exception as e:
                logger.warning(f"music: loop-extend пропущен ({e}) — оставляю music.mp3 как есть")
            task.music_path = str(existing_music)
            return
        from backend.pipeline.music_select import build_music_bed
        # На Railway /app/data — персистентный том, он затеняет запечённое в образе.
        # Поэтому house_music лежит в assets/ (вне тома); data/ — локальный фолбэк.
        candidates = [PROJECT_ROOT / "assets" / "house_music", DATA_DIR / "house_music"]
        house = next((c for c in candidates if c.exists() and any(c.glob("*.mp3"))), None)
        pool = sorted(house.glob("*.mp3")) if house else []
        # Фильтр по настроению канала — чтобы vi не получал finance_corporate_dark.
        mood_kw = {
            "documentary": ["analytical", "news", "investigation", "data", "finance", "corporate", "dark", "atmospheric"],
            "calm": ["reflective", "piano", "historical", "thoughtful", "personal", "ambient", "serenity", "soothing", "meditation", "valley", "forest"],
        }
        try:
            mood = (get_channel_config(task.lang) or {}).get("music_mood", "")
        except Exception:
            mood = ""
        if mood_kw.get(mood):
            filt = [p for p in pool if any(k in p.name.lower() for k in mood_kw[mood])]
            if filt:
                pool = filt
                logger.info(f"music: канал {task.lang} mood={mood} → {len(pool)} треков из {house.name}")
        dur = task.voiceover_duration or float(task.duration_minutes * 60)
        out = task.workspace / "music.mp3"
        # Бэйкаем на ПОЛНОЙ громкости (volume=1.0): приглушение делается ОДИН раз ниже
        # (fcpxml adjust-volume / _mix_audio). Раньше было двойное приглушение
        # (бэйк 0.12 × ещё -18.4dB в DaVinci ≈ -36dB) → музыку почти не слышно.
        if pool and build_music_bed(pool, dur, out, volume=1.0):
            task.music_path = str(out)
        else:
            task.music_path = None
            logger.warning("music: house-пул пуст или сборка не удалась → без музыки")
    
    async def _phase_assembly(self, task: VideoTask):
        """Phase 7: Assemble final output.

        output_mode="rendered" → assemble_video (FFmpeg mp4, autopilot)
        output_mode="fcpxml"  → build_fcpxml (DaVinci timeline, semi-auto)
        """
        with open(task.clip_map_path) as f:
            clip_map = json.load(f)

        if task.output_mode == "fcpxml":
            from backend.pipeline.fcpxml_export import build_fcpxml
            fcpxml_path = build_fcpxml(
                workspace=task.workspace,
                clips=clip_map,
                voiceover_path=Path(task.voiceover_path),
                music_path=Path(task.music_path) if task.music_path else None,
                project_name=f"{task.topic[:60]} [{task.lang}]",
                event_name=f"YT Factory {task.lang.upper()}",
            )
            task.final_video_path = str(fcpxml_path)
            return

        from backend.pipeline.assembly import assemble_video
        final_path = await assemble_video(
            clips=clip_map,
            voiceover=task.voiceover_path,
            music=task.music_path,
            music_volume=0.22,  # ~-13dB: слышно под голосом (было 0.12 + двойное приглушение)
            output_path=task.workspace / f"final_{task.lang}.mp4",
            style=task.style,
        )
        task.final_video_path = str(final_path)
    
    async def _phase_metadata(self, task: VideoTask):
        """Phase 8: Generate YouTube metadata (title, description, tags)."""
        from backend.pipeline.metadata import generate_metadata, build_publish_md
        # Перевод (мульти-язык): НЕ генерим заново — generate_metadata(lang=de) тянет
        # get_channel_config('de')=finance (financ-ниша + editorial-фотопревью). Вместо
        # этого переводим curiosity-метаданные источника (тон/ниша сохранены, дёшево).
        metadata = None
        if task.is_translation:
            try:
                from backend.pipeline.metadata import translate_metadata
                cp_now = json.loads((task.workspace / "checkpoint.json").read_text(encoding="utf-8"))
                src_meta = cp_now.get("src_metadata") or {}
                src_lang = cp_now.get("src_lang") or "es"
                if src_meta:
                    metadata = await translate_metadata(src_meta, src_lang, task.lang)
            except Exception as e:
                logger.warning(f"translate_metadata не удался ({e}) → генерирую метаданные заново")
                metadata = None
        if metadata is None:
            script_path = task.improved_script_path or task.script_path
            script_text = Path(script_path).read_text(encoding="utf-8")
            metadata = await generate_metadata(
                topic=task.topic,
                script=script_text,
                lang=task.lang,
                chapters=_chapters_from_aligned_plan(task.workspace),
            )
        path = task.workspace / f"metadata_{task.lang}.json"
        with open(path, "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        task.metadata_path = str(path)

        # Человекочитаемый файл для копипаста в YouTube (попадёт в zip)
        try:
            (task.workspace / f"PUBLISH_{task.lang}.md").write_text(
                build_publish_md(metadata, task.lang), encoding="utf-8")
        except Exception as e:
            logger.warning(f"PUBLISH.md не записан: {e}")

        # Авто-превью ОТКЛЮЧЕНО: клиент делает превью сам по промптам из metadata/PUBLISH
        # (стиль AxenCool, i2i с референсом вручную). Экономим fal ($0.03/видео) и не плодим
        # лишние обложки. thumbnail_prompts (текст) в метаданных генерятся как обычно — их и юзает клиент.
        if False and task.visual_mode == "stick_figure" and (not task.keep_visuals or task.is_translation):
            try:
                from backend.pipeline.stick_figure import generate_thumbnail
                # для перевода берём переведённый тайтл (концепт превью на целевом языке)
                thumb_topic = task.topic
                if task.is_translation and metadata.get("titles"):
                    thumb_topic = metadata["titles"][0]
                thumb = await generate_thumbnail(thumb_topic, task.lang, task.workspace)
                if thumb:
                    logger.info(f"thumbnail.png готов для {task.task_id}")
            except Exception as e:
                logger.warning(f"авто-превью пропущено: {e}")
        
        # Save metadata to checkpoint so API can return titles/description/tags
        cp_path = task.workspace / "checkpoint.json"
        if cp_path.exists():
            with open(cp_path) as _f:
                cp_data = json.load(_f)
            cp_data["metadata"] = metadata
            with open(cp_path, "w") as _f:
                json.dump(cp_data, _f, indent=2, ensure_ascii=False)


    async def _phase_delivery(self, task: VideoTask):
        """Phase 10: zip workspace → GDrive → Telegram notify.

        Sergey получает Telegram-сообщение со ссылкой на готовый zip в GDrive.
        Скачивает на маке, двойной клик open-davinci.command, работает в DaVinci.
        """
        from backend.pipeline.delivery import deliver
        meta = {
            "topic": task.topic,
            "lang": task.lang,
            "duration_minutes": task.duration_minutes,
        }
        result = await deliver(task.workspace, meta)
        # Сохраняем линк в checkpoint
        cp_path = task.workspace / "checkpoint.json"
        if cp_path.exists():
            import json
            with open(cp_path) as _f:
                cp_data = json.load(_f)
            cp_data["delivery"] = result
            with open(cp_path, "w") as _f:
                json.dump(cp_data, _f, indent=2, ensure_ascii=False)
        task.gdrive_url = result.get("gdrive_link", "")

        # zip собран → сырые медиа в workspace дублируют его и забивают том
        # (5ГБ-том меньше одного прогона). Чистим клипы/аудио, оставляя
        # checkpoint/metadata/PUBLISH/сценарии — листинг и /download работают.
        try:
            freed = 0
            for p in task.workspace.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".mp4", ".mp3", ".wav", ".png", ".jpg", ".jpeg"):
                    freed += p.stat().st_size
                    p.unlink(missing_ok=True)
            logger.info(f"post-delivery cleanup: освобождено {freed/1024/1024:.0f} MB")
        except Exception as e:
            logger.warning(f"post-delivery cleanup пропущен: {e}")
