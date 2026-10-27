"""
FFmpeg video assembly.

Features:
- Clip normalization (1920x1080, 30fps, H.264)
- Unified color grading (LUT or colorbalance)
- Fade transitions between clips
- Audio mixing (voiceover 100% + music 10-15%)
- Mood-based music volume adjustment
"""

import asyncio
import subprocess
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


async def assemble_video(
    clips: list[dict],
    voiceover: str,
    music: str = None,
    music_volume: float = 0.12,
    output_path: Path = None,
    style: str = "documentary",
) -> Path:
    """
    Assemble final video from clips, voiceover, and music.
    
    Args:
        clips: List of clip metadata from download phase
        voiceover: Path to voiceover audio
        music: Path to background music (optional)
        music_volume: Music volume (0.0-1.0), default 12%
        output_path: Output video path
        style: Visual style (documentary, cinematic, clean)
    
    Returns:
        Path to final video
    """
    output_path = Path(output_path)
    temp_dir = output_path.parent / "_temp_assembly"
    temp_dir.mkdir(exist_ok=True)
    
    # Phase 1: Normalize all clips
    normalized = []
    missing = []
    for i, clip in enumerate(clips):
        clip_path = Path(clip["path"])
        if not clip_path.exists():
            missing.append(clip_path.name)
            logger.warning(f"Clip not found: {clip_path}")
            continue

        norm_path = temp_dir / f"norm_{i:03d}.mp4"
        # slot_sec covers the full gap to the next scene (including any inter-scene pause).
        # Falling back to scene_end - scene_start keeps old checkpoints compatible.
        scene_duration = clip.get("slot_sec") or (clip.get("scene_end", 0) - clip.get("scene_start", 0))
        scene_duration = max(0.5, scene_duration)  # guard: -t 0 crashes ffmpeg

        await asyncio.to_thread(
            _normalize_clip, clip_path, norm_path, scene_duration, style,
            clip.get("source", ""))
        normalized.append(norm_path)

    if not normalized:
        raise RuntimeError("No clips to assemble")
    # Guard: молчаливый пропуск клипов = дыры на таймлайне. Немного потерь
    # терпимо (reuse прикрывает), >5% — явный сбой, лучше упасть чем выпустить брак.
    if len(missing) > max(2, len(clips) * 0.05):
        raise RuntimeError(
            f"{len(missing)}/{len(clips)} клипов из clip_map отсутствуют на диске: "
            f"{missing[:10]}... — сборка остановлена (битый clip_download?)")
    
    # Phase 2: Concatenate clips
    concat_path = temp_dir / "concat.mp4"
    await asyncio.to_thread(_concat_clips, normalized, concat_path)
    
    # Phase 3: Mix audio
    await asyncio.to_thread(
        _mix_audio,
        concat_path, voiceover, music, music_volume, output_path,
    )
    
    # Cleanup temp
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    # Log result
    duration = _get_duration(output_path)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"Final video: {duration:.0f}s ({duration/60:.1f} min), {size_mb:.0f} MB")
    
    return output_path


def _normalize_clip(input_path: Path, output_path: Path, target_duration: float, style: str,
                    source: str = ""):
    """Normalize a single clip: scale, fps, color grade, trim/loop to target duration."""

    # Build video filter
    filters = [
        "scale=1920:1080:force_original_aspect_ratio=decrease",
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
        "fps=30",
        "setsar=1",
    ]

    # Remotion-графика, stick-figure и doodle — чистый материал без цветокора:
    # crop/noise/vignette портят белый фон и чёткие линии скетчей/графики.
    is_remotion = source in ("remotion", "stick_figure", "doodle")

    if not is_remotion:
        # Style-specific color grading
        if style == "documentary":
            filters.append("colorbalance=rs=-0.05:gs=0.0:bs=0.05")  # Slight cool tones
            filters.append("eq=contrast=1.05:brightness=0.02:saturation=0.95")
        elif style == "cinematic":
            filters.append("colorbalance=rs=0.1:gs=-0.05:bs=0.15")  # Teal & orange
            filters.append("eq=contrast=1.1:brightness=-0.02:saturation=0.9")
        # clean = no color grading

        # Overlay effects to disguise stock footage origin
        # 1. Slight crop + zoom (removes watermark zones, changes framing)
        filters.append("crop=iw*0.92:ih*0.92:iw*0.04:ih*0.04")
        filters.append("scale=1920:1080")
        # 2. Film grain (subtle noise overlay)
        filters.append("noise=alls=8:allf=t")
        # 3. Vignette (darkened edges, cinematic feel)
        filters.append("vignette=PI/5")
        # 4. Slight sharpening (counters stock softness)
        filters.append("unsharp=3:3:0.5")

        # Fade in (0.3s) — только для стока; remotion стартует с готового фона
        filters.append("fade=t=in:st=0:d=0.3")
    if target_duration > 1:
        filters.append(f"fade=t=out:st={max(0, target_duration - 0.3):.2f}:d=0.3")
    
    vf = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-t", str(target_duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-an",  # Strip audio
        "-movflags", "+faststart",
        str(output_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg normalize error: {result.stderr.decode(errors='replace')[-500:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)


def _concat_clips(clip_paths: list[Path], output_path: Path):
    """Concatenate normalized clips using FFmpeg concat demuxer."""
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg concat error: {result.stderr.decode(errors='replace')[-500:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    concat_list.unlink(missing_ok=True)


def _mix_audio(video: Path, voiceover: str, music: str, music_volume: float, output: Path):
    """Mix voiceover and music onto video."""
    if music and Path(music).exists():
        # Video + voiceover + music
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(voiceover),
            "-i", str(music),
            "-filter_complex",
            f"[2:a]volume={music_volume},afade=t=in:st=0:d=3,areverse,afade=t=in:st=0:d=3,areverse[bg];"
            f"[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            str(output),
        ]
    else:
        # Video + voiceover only
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(voiceover),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            str(output),
        ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg mix error: {result.stderr.decode(errors='replace')[-500:]}")
        raise subprocess.CalledProcessError(result.returncode, cmd)


def _get_duration(path: Path) -> float:
    """Get media duration in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())
