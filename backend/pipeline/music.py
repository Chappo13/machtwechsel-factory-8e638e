"""
Background music sourcing.

Features:
- Searches Freesound.org for royalty-free instrumental tracks
- Mood-based filtering (dramatic, calm, dark, uplifting)
- Duration matching
- Fallback to local library
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from backend.config import FREESOUND_API_KEY, MUSIC_DIR

logger = logging.getLogger(__name__)

MOOD_QUERIES = {
    "dramatic": "dramatic cinematic instrumental orchestral",
    "calm": "calm ambient piano instrumental background",
    "dark": "dark suspense thriller instrumental cinematic",
    "uplifting": "uplifting motivational corporate instrumental",
    "neutral": "documentary background music instrumental",
    "tense": "tension suspense cinematic instrumental",
    "auto": "documentary cinematic instrumental background",
}


async def find_music(
    mood: str = "auto",
    duration: float = 1200,
    output_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Find and download background music matching the mood.
    
    Args:
        mood: Music mood (dramatic, calm, dark, uplifting, neutral, auto)
        duration: Target video duration in seconds
        output_dir: Where to save music file
    
    Returns:
        Path to music file, or None if not found
    """
    # Check local cache first
    cached = _check_cache(mood)
    if cached:
        logger.info(f"Using cached music: {cached.name}")
        return cached
    
    if not FREESOUND_API_KEY:
        logger.warning("No FREESOUND_API_KEY, skipping music")
        return None
    
    query = MOOD_QUERIES.get(mood, MOOD_QUERIES["auto"])
    min_duration = min(duration * 0.5, 120)  # At least 2 min or half video
    
    try:
        url = "https://freesound.org/apiv2/search/text/"
        params = {
            "query": query,
            "token": FREESOUND_API_KEY,
            "fields": "id,name,duration,previews,tags",
            "filter": f"duration:[{min_duration} TO 600]",
            "sort": "rating_desc",
            "page_size": 10,
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        
        results = data.get("results", [])
        
        # Filter: no vocals, no speech
        for track in results:
            tags = track.get("tags", [])
            if any(t in tags for t in ["vocals", "voice", "speech", "singing"]):
                continue
            
            previews = track.get("previews", {})
            mp3_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
            if not mp3_url:
                continue
            
            # Download
            output_path = (output_dir or MUSIC_DIR) / f"music_{mood}_{track['id']}.mp3"
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as dl_client:
                resp = await dl_client.get(mp3_url)
                if resp.status_code == 200:
                    output_path.write_bytes(resp.content)
                    logger.info(f"Downloaded music: {track['name']} ({track['duration']:.0f}s)")
                    return output_path
    
    except Exception as e:
        logger.warning(f"Music search failed: {e}")
    
    return None


def _check_cache(mood: str) -> Optional[Path]:
    """Check if we have cached music for this mood."""
    pattern = f"music_{mood}_*.mp3"
    cached = list(MUSIC_DIR.glob(pattern))
    if cached:
        return cached[0]
    return None
