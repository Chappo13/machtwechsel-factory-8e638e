"""
Multi-source stock video client.

Sources (in priority order):
1. Pexels — best quality, 200 req/hour
2. Pixabay — good fallback, 100 req/min
3. Wikimedia Commons — archival footage
4. Coverr — free stock video

Features:
- Unified search interface across all sources
- Rate limiting per source
- Clip sanitation: strict 1920x1080, no audio (see _sanitize_clip)
"""

import asyncio
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

import httpx

from backend.config import PEXELS_API_KEY, PIXABAY_API_KEY

logger = logging.getLogger(__name__)

# Pexels (и его CDN) отдают 403 на запросы без User-Agent → клипы тихо не качаются.
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _sanitize_clip(path: Path) -> bool:
    """Приводит скачанный клип к контракту пайплайна: 1920x1080, БЕЗ аудио.

    Звук везде свой (voiceover+музыка), но «-an» выполнялся только в
    rendered-режиме — fcpxml-путь минует assembly, и 22/221 клипа уехали
    в DaVinci со стоковым звуком. Разрешения гуляли: 2048x1080 (DCI),
    1620x1080, 1280x720. Один chokepoint здесь закрывает все источники
    и оба режима сборки.
    """
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        has_audio = "audio" in r.stdout
        w = h = 0
        for line in r.stdout.splitlines():
            parts = line.split(",")
            if parts[0] == "video" and len(parts) >= 3:
                w, h = int(parts[1] or 0), int(parts[2] or 0)
                break
            # некоторые сборки ffprobe печатают width,height,codec_type
            if len(parts) >= 3 and parts[-1] == "video":
                w, h = int(parts[0] or 0), int(parts[1] or 0)
                break
    except Exception as e:
        logger.warning(f"_sanitize_clip: ffprobe не отработал ({e}), клип как есть")
        return True

    if (w, h) == (1920, 1080) and not has_audio:
        return True

    tmp = path.with_suffix(".sanitized.mp4")
    if (w, h) == (1920, 1080):
        # только убрать звук — remux без перекодирования, мгновенно
        cmd = ["ffmpeg", "-y", "-i", str(path), "-c:v", "copy", "-an", str(tmp)]
    else:
        # scale до покрытия 1920x1080 + центр-кроп (DCI 2048x1080 → кроп краёв,
        # 720p → апскейл; лучше мыло, чем рамки/рассинхрон форматов)
        vf = ("scale=1920:1080:force_original_aspect_ratio=increase,"
              "crop=1920:1080")
        cmd = ["ffmpeg", "-y", "-i", str(path), "-vf", vf,
               "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", str(tmp)]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)
        tmp.replace(path)
        return True
    except Exception as e:
        tmp.unlink(missing_ok=True)
        logger.warning(f"_sanitize_clip: нормализация {path.name} не удалась: {e}")
        return _is_valid_video(path)  # клип остаётся пригодным, хоть и не идеальным


def _is_valid_video(path: Path) -> bool:
    """Файл — реально декодируемое видео с видеопотоком и длительностью > 0?

    Защита от недокачанных/битых/HTML-вместо-mp4 файлов, которые ломают сборку.
    """
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type:format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return False
    if r.returncode != 0 or "video" not in r.stdout:
        return False
    for tok in r.stdout.split():
        try:
            if float(tok) > 0.3:
                return True
        except ValueError:
            continue
    return False


class MultiStockClient:
    """Unified stock video search and download client."""

    def __init__(self):
        self.sources = []
        if PEXELS_API_KEY:
            self.sources.append(PexelsSource(PEXELS_API_KEY))
        if PIXABAY_API_KEY:
            self.sources.append(PixabaySource(PIXABAY_API_KEY))
        self.sources.append(CoverrSource())
        self.sources.append(NASASource())
        # URLs already downloaded this run — prevents the same stock clip appearing twice.
        self.used_urls: set[str] = set()
        # Повторный query раньше получал ТУ ЖЕ страницу выдачи (отличие только
        # used_urls-фильтром) → 8 шотов одной сцены крутили соседние клипы одной
        # выдачи. Счётчик → page-параметр: каждое повторение уходит глубже.
        self._query_uses: dict[str, int] = {}
        # Клиент общий для всех шотов и теперь зовётся КОНКУРЕНТНО (до 3 разом из
        # download_clips). Lock защищает общий мутабельный стейт (used_urls,
        # _query_uses) от гонок — узко, без await внутри критической секции.
        self._lock = asyncio.Lock()

        if not self.sources:
            logger.warning("No stock video API keys configured!")

    async def search_and_download(
        self,
        query: str,
        min_duration: float = 5,
        output_path: Path = None,
        scene_text: str = "",
    ) -> Optional[dict]:
        """Search across sources, skip already-used URLs, download first valid clip."""
        async with self._lock:  # атомарно: страница query + инкремент счётчика
            page = 1 + self._query_uses.get(query, 0)
            self._query_uses[query] = self._query_uses.get(query, 0) + 1
        for source in self.sources:
            try:
                candidates = await source.search(query, min_duration=min_duration, page=page)
                if not candidates and page > 1:
                    # глубокая страница пустая — отдай хотя бы первую
                    candidates = await source.search(query, min_duration=min_duration)
                for result in candidates:
                    url = result["url"]
                    # Claim-before-download: занимаем URL под локом ДО скачивания,
                    # чтобы два конкурентных шота не качали один и тот же клип.
                    async with self._lock:
                        if url in self.used_urls:
                            continue
                        self.used_urls.add(url)
                    success = await source.download(url, output_path)
                    # Валидаторы — блокирующие (ffprobe/ffmpeg re-encode): через
                    # to_thread, иначе sanitize сериализует весь параллельный сток.
                    if (success and output_path.exists()
                            and output_path.stat().st_size > 10240
                            and await asyncio.to_thread(_is_valid_video, output_path)
                            and await asyncio.to_thread(_sanitize_clip, output_path)):
                        return {
                            "source": source.name,
                            "url": url,
                            "duration": result.get("duration", 0),
                            "width": result.get("width", 1920),
                            "height": result.get("height", 1080),
                        }
                    # Не вышло — освобождаем claim (пусть другой шот попробует) и чистим.
                    async with self._lock:
                        self.used_urls.discard(url)
                    if output_path and output_path.exists():
                        try:
                            output_path.unlink()
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"{source.name} failed for '{query}': {e}")
                continue

        return None


def _rendition_key(f: dict) -> tuple:
    """Сортировка renditions: точный FullHD → прочие *x1080 → 720p+ → 4K в хвосте.

    Раньше сортировали только по height — DCI 2048x1080 неотличим от 1920x1080
    (оба h=1080), отсюда разнобой форматов в выдаче. 4K не берём: 50-100 МБ/клип,
    выигрыша на 1080p-таймлайне нет.
    """
    w, h = f.get("width", 0), f.get("height", 0)
    if (w, h) == (1920, 1080):
        rank = 0
    elif h == 1080:
        rank = 1          # 2048x1080 и пр. — _sanitize_clip докропит
    elif 720 <= h < 1080:
        rank = 2
    else:
        rank = 3          # 1440p/4K — только если ничего другого нет
    return (rank, -h if rank == 2 else h)


class PexelsSource:
    """Pexels video API client."""
    
    name = "pexels"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.pexels.com/videos/search"
        self._last_request = 0
        self._req_lock = asyncio.Lock()  # race-safe rate-limit под конкуренцией
        self._min_interval = 1.5  # seconds between requests
    
    async def search(self, query: str, min_duration: float = 5, page: int = 1) -> list[dict]:
        """Search Pexels, return up to 6 HD candidates for dedup selection."""
        await self._rate_limit()

        headers = {"Authorization": self.api_key, "User-Agent": _UA}
        params = {
            "query": query,
            "per_page": 20,
            "page": page,
            "size": "large",
            "orientation": "landscape",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url, headers=headers, params=params)
            if resp.status_code == 429:
                logger.warning("Pexels rate limit hit, cooling down 60s")
                await asyncio.sleep(60)
                return []
            resp.raise_for_status()
            data = resp.json()

        candidates = []
        for video in data.get("videos", []):
            duration = video.get("duration", 0)
            if duration < min_duration:
                continue
            files = video.get("video_files", [])
            hd_files = [f for f in files if f.get("height", 0) >= 720]
            hd_files.sort(key=_rendition_key)
            if hd_files:
                best = hd_files[0]
                candidates.append({
                    "url": best["link"],
                    "duration": duration,
                    "width": best.get("width", 1920),
                    "height": best.get("height", 1080),
                })
            if len(candidates) >= 6:
                break
        return candidates
    
    async def download(self, url: str, output_path: Path) -> bool:
        """Download a video file."""
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
            if resp.status_code == 200:
                output_path.write_bytes(resp.content)
                return True
        return False

    async def _rate_limit(self):
        """Enforce rate limiting."""
        async with self._req_lock:  # под локом: иначе 2 шота читают тот же _last_request
            now = time.time()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request = time.time()


class PixabaySource:
    """Pixabay video API client."""
    
    name = "pixabay"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://pixabay.com/api/videos/"
        self._last_request = 0
        self._req_lock = asyncio.Lock()  # race-safe rate-limit под конкуренцией
        self._min_interval = 0.5
    
    async def search(self, query: str, min_duration: float = 5, page: int = 1) -> list[dict]:
        await self._rate_limit()

        params = {
            "key": self.api_key,
            "q": query,
            "per_page": 20,
            "page": page,
            "min_width": 1280,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

        candidates = []
        for hit in data.get("hits", []):
            duration = hit.get("duration", 0)
            if duration < min_duration:
                continue
            # «large» вслепую отдавал и 4K; перебираем renditions тем же ключом,
            # что и Pexels — FullHD приоритетен
            videos = hit.get("videos", {})
            renditions = [v for v in videos.values()
                          if v.get("url") and v.get("height", 0) >= 720]
            renditions.sort(key=_rendition_key)
            if renditions:
                best = renditions[0]
                candidates.append({
                    "url": best["url"],
                    "duration": duration,
                    "width": best.get("width", 1920),
                    "height": best.get("height", 1080),
                })
            if len(candidates) >= 6:
                break
        return candidates
    
    async def download(self, url: str, output_path: Path) -> bool:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
            if resp.status_code == 200:
                output_path.write_bytes(resp.content)
                return True
        return False

    async def _rate_limit(self):
        async with self._req_lock:  # под локом: иначе 2 шота читают тот же _last_request
            now = time.time()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request = time.time()


class NASASource:
    """NASA public-domain video library — no API key required.

    Uses images-api.nasa.gov. Fetches a per-item manifest to resolve the
    actual MP4 URL. Prefers ~640 resolution to keep file sizes reasonable.
    Great for documentary B-roll: cities from orbit, Earth, science, space.
    """

    name = "nasa"
    _search_url = "https://images-api.nasa.gov/search"

    async def search(self, query: str, min_duration: float = 5, page: int = 1) -> list[dict]:
        params = {"q": query, "media_type": "video", "page": page}
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                resp = await c.get(self._search_url, params=params)
                if resp.status_code != 200:
                    return []
                items = resp.json().get("collection", {}).get("items", [])
        except Exception:
            return []

        candidates = []
        for item in items[:4]:
            href = item.get("href")
            if not href:
                continue
            try:
                async with httpx.AsyncClient(timeout=15) as c:
                    manifest_resp = await c.get(href)
                    if manifest_resp.status_code != 200:
                        continue
                    files = manifest_resp.json()
                mp4s = [f for f in files if isinstance(f, str) and f.endswith(".mp4")]
                if not mp4s:
                    continue
                # ~640 на FullHD-таймлайне — мыло; берём large/medium, ~orig
                # не трогаем (бывает гигабайтным)
                chosen = next(
                    (f for f in mp4s if "~large" in f),
                    next((f for f in mp4s if "~medium" in f),
                         next((f for f in mp4s if "~640" in f), mp4s[0])),
                )
                candidates.append({"url": chosen, "duration": 20, "width": 1280, "height": 720})
                if len(candidates) >= 3:
                    break
            except Exception:
                continue
        return candidates

    async def download(self, url: str, output_path: Path) -> bool:
        try:
            async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
                resp = await c.get(url, headers={"User-Agent": _UA})
                if resp.status_code == 200:
                    output_path.write_bytes(resp.content)
                    return True
        except Exception:
            pass
        return False


class CoverrSource:
    """Coverr.co free stock video client."""

    name = "coverr"

    async def search(self, query: str, min_duration: float = 5, page: int = 1) -> list[dict]:
        """Search Coverr for stock videos."""
        params = {"query": query, "page_size": 10, "page": page}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get("https://api.coverr.co/videos", params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        except Exception:
            return []

        candidates = []
        for hit in data.get("hits", data.get("videos", [])):
            duration = hit.get("duration", 10)
            if duration < min_duration:
                continue
            urls = hit.get("urls", {})
            mp4_url = urls.get("mp4") or urls.get("mp4_download")
            if mp4_url:
                candidates.append({"url": mp4_url, "duration": duration, "width": 1920, "height": 1080})
            if len(candidates) >= 4:
                break
        return candidates
    
    async def download(self, url: str, output_path: Path) -> bool:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                output_path.write_bytes(resp.content)
                return True
        return False
