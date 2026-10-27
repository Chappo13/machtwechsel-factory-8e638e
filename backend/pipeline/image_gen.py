"""
AI image generation for B-roll fallback.

When stock footage doesn't match the narration or isn't available,
generates a photorealistic image and applies Ken Burns effect (zoom/pan)
to create a video clip.

Sources:
- fal.ai Flux (photorealistic, $0.01-0.03/image)
- Fallback: fal.ai SDXL (stylized)
"""

import asyncio
import logging
import subprocess
import random
from pathlib import Path
from typing import Optional

import httpx

from backend.config import get_model_config

logger = logging.getLogger(__name__)

# fal.ai endpoints
FAL_FLUX_URL = "https://queue.fal.run/fal-ai/flux/schnell"
FAL_FLUX_PRO_URL = "https://queue.fal.run/fal-ai/flux-pro/v1.1"


async def generate_scene_image(
    scene_text: str,
    topic: str,
    lang: str,
    output_path: Path,
    style: str = "photorealistic",
) -> Optional[Path]:
    """
    Generate an image matching the scene narration.
    
    Args:
        scene_text: What the narrator is saying during this scene
        topic: Overall video topic (for context)
        lang: Language code
        output_path: Where to save the image (.png)
        style: Image style (photorealistic, cinematic, documentary)
    
    Returns:
        Path to generated image, or None if failed
    """
    import os
    fal_key = os.getenv("FALAPI", "")
    if not fal_key:
        logger.warning("No FALAPI key, skipping image generation")
        return None
    
    # Generate image description from scene text
    prompt = await _build_image_prompt(scene_text, topic, style)

    # Модель/параметры — из swappable-конфига image_generation (Seedream v4 по
    # умолчанию; качество выше Flux Schnell). Меняется в models.yaml без правки кода.
    try:
        cfg = get_model_config("image_generation")
    except Exception:
        cfg = {}
    url = cfg.get("endpoint") or FAL_FLUX_URL
    params = cfg.get("params") or {
        "image_size": "landscape_16_9", "num_images": 1, "enable_safety_checker": False}

    try:
        headers = {
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json",
        }

        payload = {"prompt": prompt, **params}

        async with httpx.AsyncClient(timeout=90) as client:
            # Submit to queue
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            # queue.fal.run отвечает request_id, а НЕ images сразу — нужно поллить
            # статус. Старый код читал data["images"] напрямую → всегда None,
            # из-за чего сток-фолбэк по факту никогда не срабатывал.
            image_url = ""
            if "images" in data:
                image_url = (data["images"][0] or {}).get("url", "")
            elif "request_id" in data:
                request_id = data["request_id"]
                status_url = data.get("status_url") or f"{url}/requests/{request_id}/status"
                response_url = data.get("response_url") or f"{url}/requests/{request_id}"
                for _ in range(45):
                    await asyncio.sleep(2)
                    sr = await client.get(status_url, headers={"Authorization": f"Key {fal_key}"})
                    st = sr.json().get("status")
                    if st == "COMPLETED":
                        rr = await client.get(response_url, headers={"Authorization": f"Key {fal_key}"})
                        image_url = (rr.json().get("images", [{}])[0] or {}).get("url", "")
                        break
                    if st in ("FAILED", "CANCELLED"):
                        logger.warning(f"fal.ai queue {st} for {output_path.name}")
                        return None
                else:
                    logger.warning(f"fal.ai queue timeout for {output_path.name}")
                    return None

            if not image_url:
                logger.warning("No image URL in fal.ai response")
                return None

            # Download image
            img_resp = await client.get(image_url)
            if img_resp.status_code == 200:
                output_path.write_bytes(img_resp.content)
                logger.info(f"Generated image: {output_path.name} ({len(img_resp.content)//1024}KB)")
                return output_path

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return None


def apply_ken_burns(
    image_path: Path,
    output_path: Path,
    duration: float,
    effect: str = "auto",
    fps: int = 30,
) -> Path:
    """
    Apply Ken Burns effect (zoom/pan) to a still image to create video.
    
    Args:
        image_path: Input image
        output_path: Output video (.mp4)
        duration: Target duration in seconds
        effect: Effect type (zoom_in, zoom_out, pan_left, pan_right, auto)
        fps: Frames per second
    
    Returns:
        Path to output video
    """
    if effect == "auto":
        effect = random.choice(["zoom_in", "zoom_out", "pan_left", "pan_right"])
    
    total_frames = int(duration * fps)
    
    # Build zoompan filter based on effect
    if effect == "zoom_in":
        # Slow zoom in from 100% to 120%
        zp = f"zoompan=z='min(zoom+0.0008,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
    elif effect == "zoom_out":
        # Start at 120%, zoom out to 100%
        zp = f"zoompan=z='if(eq(on,1),1.2,max(zoom-0.0008,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
    elif effect == "pan_left":
        # Pan from right to left
        zp = f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)+iw/zoom/2*on/{total_frames}':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
    elif effect == "pan_right":
        # Pan from left to right  
        zp = f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)-iw/zoom/2*on/{total_frames}':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
    else:
        zp = f"zoompan=z='min(zoom+0.0008,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}"
    
    # Быстрый Ken Burns: pre-scale до 1080p (zoompan не пере-масштабирует из нативного
    # размера каждый кадр) + preset ultrafast (~5-8x быстрее на слабом CPU) + threads под
    # параллельную сборку. medium давал ~30с/клип на Railway = 44 мин на 88 сцен.
    vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,{zp}"
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        "-threads", "2",
        str(output_path),
    ]
    
    # timeout обязателен: ffmpeg zoompan на «кривом» изображении может зависнуть навечно
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error(f"Ken Burns FFmpeg error: {result.stderr[:500]}")
        raise RuntimeError(f"Ken Burns effect failed: {result.stderr[:200]}")
    
    logger.info(f"Ken Burns: {effect}, {duration:.1f}s → {output_path.name}")
    return output_path


async def generate_clip_fallback(
    scene_text: str,
    topic: str,
    lang: str,
    duration: float,
    output_path: Path,
) -> Optional[Path]:
    """
    Full fallback pipeline: generate image → apply Ken Burns → video clip.
    
    Used when stock footage search fails for a scene.
    
    Args:
        scene_text: Scene narration text
        topic: Video topic
        lang: Language code
        duration: Target clip duration
        output_path: Output video path (.mp4)
    
    Returns:
        Path to video clip, or None if failed
    """
    image_path = output_path.with_suffix(".png")
    
    # Step 1: Generate image
    result = await generate_scene_image(
        scene_text=scene_text,
        topic=topic,
        lang=lang,
        output_path=image_path,
    )
    
    if not result:
        return None
    
    # Step 2: Apply Ken Burns effect
    try:
        video_path = apply_ken_burns(
            image_path=image_path,
            output_path=output_path,
            duration=duration,
        )
        
        # Cleanup image
        image_path.unlink(missing_ok=True)
        
        return video_path
    except Exception as e:
        logger.error(f"Ken Burns fallback failed: {e}")
        image_path.unlink(missing_ok=True)
        return None


async def _build_image_prompt(scene_text: str, topic: str, style: str) -> str:
    """
    Convert scene narration into an image generation prompt.
    Uses LLM to extract the visual essence of the scene.
    """
    from backend.utils.llm import call_llm
    
    model_config = get_model_config("scene_tagging")
    
    response = await call_llm(
        prompt=f"""Convert this documentary narration into a single image description for stock-photo-style image generation.

Topic: {topic}
Scene text: {scene_text[:500]}

Rules:
- Describe what should be VISIBLE in the image (not concepts)
- Style: {style}, high quality, 16:9 aspect ratio
- No text, no watermarks, no people's faces (unless historical figure)
- Think "what would a documentary show on screen while this is being said?"
- Keep it under 100 words
- English only

Return ONLY the image description, nothing else.""",
        model=model_config["primary"],
        temperature=0.6,
        max_tokens=200,
    )
    
    return response.strip()
