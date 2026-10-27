"""
Music Client — поиск и скачивание фоновой музыки

Использует Pixabay Music API для поиска royalty-free треков.

Использование:
    from music_client import search_music, download_music, get_music_for_theme

    # Поиск по запросу
    tracks = search_music("dark ambient cinematic", per_page=5)

    # Получить музыку под тему
    track_path = get_music_for_theme("egypt", duration_needed=300, output_dir=Path("music"))
"""

import os
import json
import random
import requests
from pathlib import Path
from typing import Optional, List, Dict
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
from dotenv import load_dotenv

load_dotenv()

# Freesound.org API (бесплатно, регистрация на freesound.org/apiv2/apply)
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")
FREESOUND_BASE_URL = "https://freesound.org/apiv2"

# Legacy Pixabay (не работает для музыки, но оставляем на всякий)
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

DATA_DIR = Path(__file__).parent.parent / "data"
MUSIC_DIR = DATA_DIR / "music"
MUSIC_CACHE_FILE = MUSIC_DIR / "cache.json"

# Маппинг тем на поисковые запросы для музыки
# Порядок важен: первые запросы — самые точные для атмосферы
THEME_MUSIC_QUERIES = {
    "egypt": [
        "mysterious ancient",           # Таинственная атмосфера древности
        "dark cinematic tension",       # Напряжение для документалки
        "epic orchestral dramatic",     # Эпичность для пирамид
        "ambient desert",               # Пустынная атмосфера
        "documentary suspense",         # Документальный саспенс
    ],
    "conspiracy": [
        "dark tension suspense",        # Напряжённая атмосфера
        "investigation thriller",       # Расследование
        "mysterious dark ambient",      # Тёмная загадочность
        "paranoid electronic",          # Паранойя
        "documentary dramatic",         # Документальная драма
    ],
    "ufo": [
        "sci-fi dark ambient",          # Научная фантастика
        "space mysterious",             # Космическая тайна
        "alien electronic",             # Инопланетная атмосфера
        "cosmic suspense",              # Космический саспенс
        "ethereal ambient",             # Эфирность
    ],
    "history": [
        "epic cinematic orchestral",    # Эпичная оркестровка
        "documentary dramatic",         # Документальная драма
        "ancient mysterious",           # Древняя загадка
        "historical ambient",           # Историческая атмосфера
        "emotional piano",              # Эмоциональное пиано
    ],
    "general": [
        "cinematic ambient",            # Кинематографичность
        "documentary background",       # Фон для документалки
        "mysterious atmospheric",       # Атмосферная загадочность
        "dramatic tension",             # Драматическое напряжение
        "dark ambient"                  # Тёмный эмбиент
    ]
}

# Категории Pixabay для фильтрации
THEME_CATEGORIES = {
    "egypt": "backgrounds",      # Фоновая музыка
    "conspiracy": "backgrounds",
    "ufo": "science fiction",
    "history": "backgrounds",
    "general": "backgrounds"
}

# Per-track volume adjustments (some tracks are louder than others)
# Default is 0.06 (6%), but some tracks need different levels
MUSIC_VOLUMES = {
    # === Старые треки (проверенные) ===
    "dark_mystery_584.mp3": 0.15,
    "documentary_atmospheric_551.mp3": 0.15,
    "ambient_meditation_441.mp3": 0.15,
    "space_ambient_660.mp3": 0.15,
    "ambient_valley_127.mp3": 0.15,
    "piano_nervious.mp3": 0.15,
    "Street_Museum_(Dark_Ambient_BG_726368.mp3": 0.15,
    "Ambient_Serenity_Flow_795724.mp3": 0.15,
    "Drone_ambience,_A_546360.mp3": 0.12,
    "Floating_Ambient_Soundscape_795906.mp3": 0.15,
    "Road_In_The_Forest_439553.mp3": 0.15,
    "Soothing_Atmospheric_Sound_797914.mp3": 0.15,
    # === Новые: dark_mystery ===
    "dark_mystery_DSGNDron_Atonal_Mysterious_Atm_652714.mp3": 0.15,
    "dark_mystery_Terrible_Mistake_592817.mp3": 0.10,
    "dark_mystery_Suspense_Dark_Scary_Atmosphere_712111.mp3": 0.15,
    "dark_mystery_Rogue_Planet_(mystery_ambient)_625744.mp3": 0.15,
    # === Новые: cosmic ===
    "cosmic_Dark_Post_Apocalyptic_Backgrou_490526.mp3": 0.15,
    "cosmic_drone6.wav_272595.mp3": 0.12,
    "cosmic_Alesis_QS8_Spooky_Robot_725063.mp3": 0.15,
    "cosmic_Floating_In_Space__-_bpm_78_lo_749758.mp3": 0.15,
    # === Новые: documentary ===
    "documentary_Thriller_Documentary_Pack_#1_435370.mp3": 0.15,
    "documentary_Sad_Emotional_-_bpm_86_loop_719045.mp3": 0.15,
    "documentary_This_song_is_good.mp3_434153.mp3": 0.15,
    "documentary_Emotional_Piano_and_Violin_744877.mp3": 0.15,
    # === Новые: calm_ambient ===
    "calm_ambient_terrace_ambience_01.wav_170584.mp3": 0.15,
    "calm_ambient_city_night_hum_07_160927_0989._506019.mp3": 0.12,
    "calm_ambient_Calm_Ambient_Soundscape_for_Pr_797701.mp3": 0.15,
    "calm_ambient_Tibetan-Bell-Jupiter-Moon_Push_208772.mp3": 0.15,
}
DEFAULT_MUSIC_VOLUME = 0.15  # 15% for unknown tracks

# BLACKLIST тегов — исключаем voiceover, речь, аудиокниги
# Эти теги означают, что это НЕ фоновая музыка
BLACKLIST_TAGS = {
    # Голос/речь
    "voice", "voiceover", "voice-over", "vocal", "vocals",
    "speech", "speaking", "spoken", "talk", "talking",
    "narration", "narrator", "narrated",
    # Аудиокниги/подкасты
    "audiobook", "audio-book", "podcast", "radio",
    "reading", "story", "storytelling",
    # Человек
    "human", "male", "female", "man", "woman", "actor",
    "british", "american", "english",
    # Другое нежелательное
    "lecture", "interview", "dialogue", "conversation",
    "announcement", "commercial", "advertisement"
}


def search_music(
    query: str,
    per_page: int = 20,
    min_duration: int = 60,
    max_duration: int = 600,
    category: str = None
) -> List[Dict]:
    """
    Поиск музыки через Freesound.org API.

    Freesound — бесплатный репозиторий звуков и музыки под CC лицензией.
    Регистрация: https://freesound.org/apiv2/apply/

    Args:
        query: Поисковый запрос
        per_page: Количество результатов
        min_duration: Минимальная длительность (сек)
        max_duration: Максимальная длительность (сек)
        category: Не используется (для совместимости)

    Returns:
        Список треков с метаданными
    """
    if not FREESOUND_API_KEY:
        print("⚠ FREESOUND_API_KEY not set!")
        print("  1. Register at: https://freesound.org/apiv2/apply/")
        print("  2. Create an API credential")
        print("  3. Add to .env: FREESOUND_API_KEY=your_key")
        return []

    # Добавляем фильтры для музыки (не звуковые эффекты)
    # duration:[min TO max] — фильтр по длительности в секундах
    filter_str = f"duration:[{min_duration} TO {max_duration}]"

    params = {
        "token": FREESOUND_API_KEY,
        "query": query,
        "page_size": per_page,
        "filter": filter_str,
        "sort": "downloads_desc",  # Популярные первые
        "fields": "id,name,duration,tags,previews,download,num_downloads,avg_rating,license"
    }

    try:
        response = requests.get(
            f"{FREESOUND_BASE_URL}/search/text/",
            params=params,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            # Нормализуем структуру и фильтруем
            tracks = []
            filtered_count = 0

            for r in results:
                # Получаем теги и проверяем blacklist
                tags = r.get("tags", [])
                tags_lower = {t.lower() for t in tags}

                # Пропускаем треки с голосом/речью/аудиокнигами
                if tags_lower & BLACKLIST_TAGS:
                    filtered_count += 1
                    continue

                # Получаем URL для скачивания (preview или полный)
                previews = r.get("previews", {})
                audio_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")

                tracks.append({
                    "id": r.get("id"),
                    "title": r.get("name", "Unknown"),
                    "duration": int(r.get("duration", 0)),
                    "tags": ",".join(tags),
                    "audio": audio_url,
                    "downloads": r.get("num_downloads", 0),
                    "rating": r.get("avg_rating", 0),
                    "license": r.get("license")
                })

            if filtered_count > 0:
                print(f"    Filtered out {filtered_count} voice/speech tracks")

            return tracks

        elif response.status_code == 401:
            print("✗ Invalid FREESOUND_API_KEY")
            return []
        elif response.status_code == 429:
            print("✗ Freesound rate limit exceeded")
            return []
        else:
            print(f"Freesound API error: {response.status_code}")
            return []

    except requests.exceptions.Timeout:
        print("Freesound API timeout")
        return []
    except Exception as e:
        print(f"Search error: {e}")
        return []


def search_music_fallback(
    query: str,
    per_page: int = 10,
    min_duration: int = 60,
    max_duration: int = 600
) -> List[Dict]:
    """
    Fallback поиск через Freesound API или локальный кеш.
    """
    # Проверяем локальный кеш
    if MUSIC_CACHE_FILE.exists():
        with open(MUSIC_CACHE_FILE, "r") as f:
            cache = json.load(f)

        # Ищем подходящие треки в кеше
        matching = []
        query_words = set(query.lower().split())

        for track in cache.get("tracks", []):
            track_tags = set(track.get("tags", "").lower().split(","))
            if query_words & track_tags:  # Пересечение
                if min_duration <= track.get("duration", 0) <= max_duration:
                    matching.append(track)

        return matching[:per_page]

    return []


def download_music(url: str, output_path: Path) -> bool:
    """
    Скачать музыкальный файл.

    Args:
        url: URL для скачивания
        output_path: Путь сохранения

    Returns:
        True если успешно
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        with open(output_path, 'wb') as f:
            if tqdm is not None:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=output_path.name) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            else:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        return output_path.exists() and output_path.stat().st_size > 0

    except Exception as e:
        print(f"Download error: {e}")
        return False


def get_music_for_theme(
    theme: str,
    duration_needed: float,
    output_dir: Path = None,
    prefer_longer: bool = True
) -> Optional[Path]:
    """
    Получить подходящую музыку для темы.

    Выбирает атмосферную музыку, которая:
    - Соответствует теме (mysterious для egypt, suspense для conspiracy)
    - Достаточно длинная (меньше повторов)
    - Популярная (проверено качество)

    Args:
        theme: Тема видео (egypt, conspiracy, ufo, history)
        duration_needed: Нужная длительность в секундах
        output_dir: Директория для сохранения
        prefer_longer: Предпочитать длинные треки (меньше повторов)

    Returns:
        Путь к скачанному файлу или None
    """
    output_dir = output_dir or MUSIC_DIR
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Получаем запросы и категорию для темы
    queries = THEME_MUSIC_QUERIES.get(theme, THEME_MUSIC_QUERIES["general"])
    category = THEME_CATEGORIES.get(theme, "backgrounds")

    all_tracks = []

    # Собираем треки по всем запросам
    for query in queries[:3]:  # Первые 3 — самые релевантные
        print(f"  Searching: '{query}'...")

        # Для длинных видео ищем длинные треки (меньше повторов = лучше)
        min_dur = 120 if duration_needed > 180 else 60
        max_dur = 600  # 10 минут макс

        tracks = search_music(
            query=query,
            per_page=15,
            min_duration=min_dur,
            max_duration=max_dur,
            category=category
        )

        if tracks:
            all_tracks.extend(tracks)
            print(f"    Found {len(tracks)} tracks")

    if not all_tracks:
        print(f"No music found for theme: {theme}")
        return None

    # Удаляем дубликаты по ID
    seen_ids = set()
    unique_tracks = []
    for t in all_tracks:
        if t.get("id") not in seen_ids:
            seen_ids.add(t.get("id"))
            unique_tracks.append(t)

    # Сортируем: длинные + популярные в приоритете
    if prefer_longer:
        unique_tracks.sort(
            key=lambda x: (x.get("duration", 0) * 0.7 + (x.get("downloads", 0) + x.get("likes", 0)) * 0.3),
            reverse=True
        )

    # Выбираем из топ-5 случайно (для разнообразия)
    top_tracks = unique_tracks[:5]
    track = random.choice(top_tracks) if len(top_tracks) > 1 else top_tracks[0]

    # Скачиваем
    audio_url = track.get("audio") or track.get("previewURL")
    if not audio_url:
        print("No download URL available")
        return None

    track_id = track.get("id", random.randint(1000, 9999))
    safe_title = track.get("title", "track").replace(" ", "_")[:20]
    filename = f"{theme}_{safe_title}_{track_id}.mp3"
    output_path = output_dir / filename

    # Проверяем кеш
    if output_path.exists() and output_path.stat().st_size > 10000:
        print(f"✓ Using cached: {filename}")
        return output_path

    print(f"✓ Selected: {track.get('title', 'Unknown')} ({track.get('duration', 0)}s)")
    print(f"  Downloading...")

    if download_music(audio_url, output_path):
        # Сохраняем в кеш
        save_to_cache(track, output_path)
        print(f"  Saved: {output_path.name}")
        return output_path

    return None


def get_music_volume(music_path: Path) -> float:
    """
    Получить рекомендуемую громкость для музыкального файла.

    Некоторые треки громче других, поэтому нужна индивидуальная настройка.

    Args:
        music_path: Путь к файлу музыки

    Returns:
        Рекомендуемая громкость (0.0-1.0)
    """
    if music_path is None:
        return DEFAULT_MUSIC_VOLUME

    filename = Path(music_path).name
    return MUSIC_VOLUMES.get(filename, DEFAULT_MUSIC_VOLUME)


def get_local_music(theme: str, output_dir: Path = None) -> Optional[Path]:
    """
    Получить локальную музыку из папки data/music/ по теме.

    Использует курированные файлы, подобранные под каждую тему.
    НЕ энергичную музыку — спокойную, атмосферную.

    Args:
        theme: Тема для фильтрации
        output_dir: Директория с музыкой

    Returns:
        Путь к файлу или None
    """
    # Маппинг тем к подходящим файлам (приоритет по порядку)
    THEME_LOCAL_MUSIC = {
        "egypt": [
            "dark_mystery_584.mp3",
            "dark_mystery_DSGNDron_Atonal_Mysterious_Atm_652714.mp3",
            "dark_mystery_Suspense_Dark_Scary_Atmosphere_712111.mp3",
            "documentary_atmospheric_551.mp3",
            "ambient_meditation_441.mp3",
        ],
        "forbidden_history": [
            "dark_mystery_584.mp3",
            "dark_mystery_Terrible_Mistake_592817.mp3",
            "dark_mystery_Rogue_Planet_(mystery_ambient)_625744.mp3",
            "documentary_atmospheric_551.mp3",
            "Street_Museum_(Dark_Ambient_BG_726368.mp3",
        ],
        "conspiracy": [
            "dark_mystery_584.mp3",
            "dark_mystery_DSGNDron_Atonal_Mysterious_Atm_652714.mp3",
            "dark_mystery_Suspense_Dark_Scary_Atmosphere_712111.mp3",
            "documentary_Thriller_Documentary_Pack_#1_435370.mp3",
            "documentary_atmospheric_551.mp3",
        ],
        "ufo": [
            "space_ambient_660.mp3",
            "cosmic_Dark_Post_Apocalyptic_Backgrou_490526.mp3",
            "cosmic_Alesis_QS8_Spooky_Robot_725063.mp3",
            "cosmic_Floating_In_Space__-_bpm_78_lo_749758.mp3",
            "dark_mystery_584.mp3",
            "Drone_ambience,_A_546360.mp3",
        ],
        "space": [
            "space_ambient_660.mp3",
            "cosmic_Floating_In_Space__-_bpm_78_lo_749758.mp3",
            "cosmic_drone6.wav_272595.mp3",
            "cosmic_Alesis_QS8_Spooky_Robot_725063.mp3",
            "Floating_Ambient_Soundscape_795906.mp3",
            "Drone_ambience,_A_546360.mp3",
        ],
        "blackhole": [
            "cosmic_Dark_Post_Apocalyptic_Backgrou_490526.mp3",
            "cosmic_drone6.wav_272595.mp3",
            "space_ambient_660.mp3",
            "Drone_ambience,_A_546360.mp3",
            "dark_mystery_584.mp3",
        ],
        "history": [
            "documentary_atmospheric_551.mp3",
            "documentary_Thriller_Documentary_Pack_#1_435370.mp3",
            "documentary_Sad_Emotional_-_bpm_86_loop_719045.mp3",
            "documentary_Emotional_Piano_and_Violin_744877.mp3",
            "ambient_meditation_441.mp3",
        ],
        "war": [
            "documentary_atmospheric_551.mp3",
            "documentary_Thriller_Documentary_Pack_#1_435370.mp3",
            "dark_mystery_584.mp3",
            "dark_mystery_Terrible_Mistake_592817.mp3",
            "documentary_Sad_Emotional_-_bpm_86_loop_719045.mp3",
        ],
        "tech": [
            "ambient_meditation_441.mp3",
            "calm_ambient_terrace_ambience_01.wav_170584.mp3",
            "calm_ambient_Calm_Ambient_Soundscape_for_Pr_797701.mp3",
            "Ambient_Serenity_Flow_795724.mp3",
            "documentary_This_song_is_good.mp3_434153.mp3",
        ],
        "health": [
            "Soothing_Atmospheric_Sound_797914.mp3",
            "calm_ambient_Calm_Ambient_Soundscape_for_Pr_797701.mp3",
            "calm_ambient_Tibetan-Bell-Jupiter-Moon_Push_208772.mp3",
            "ambient_meditation_441.mp3",
            "calm_ambient_terrace_ambience_01.wav_170584.mp3",
        ],
        "business": [
            "documentary_This_song_is_good.mp3_434153.mp3",
            "documentary_Emotional_Piano_and_Violin_744877.mp3",
            "ambient_meditation_441.mp3",
            "Ambient_Serenity_Flow_795724.mp3",
            "calm_ambient_terrace_ambience_01.wav_170584.mp3",
        ],
        "races": [
            "documentary_Sad_Emotional_-_bpm_86_loop_719045.mp3",
            "ambient_valley_127.mp3",
            "calm_ambient_city_night_hum_07_160927_0989._506019.mp3",
            "ambient_meditation_441.mp3",
        ],
        "general": [
            "documentary_atmospheric_551.mp3",
            "documentary_Thriller_Documentary_Pack_#1_435370.mp3",
            "ambient_meditation_441.mp3",
            "calm_ambient_Calm_Ambient_Soundscape_for_Pr_797701.mp3",
            "piano_nervious.mp3",
        ],
    }

    # Папка с курированной музыкой
    curated_dir = Path(__file__).parent.parent / "data" / "music"

    if not curated_dir.exists():
        return None

    # Получаем список файлов для темы
    theme_files = THEME_LOCAL_MUSIC.get(theme, THEME_LOCAL_MUSIC["general"])

    # Проверяем какие файлы существуют
    available = []
    for filename in theme_files:
        filepath = curated_dir / filename
        if filepath.exists():
            available.append(filepath)

    if available:
        # Выбираем случайно из доступных (для разнообразия)
        selected = random.choice(available)
        print(f"  ✓ Using curated music: {selected.name}")
        return selected

    # Fallback: любой mp3 из папки (кроме epic_drums — слишком энергичный)
    all_files = [f for f in curated_dir.glob("*.mp3") if "epic_drums" not in f.name]

    if all_files:
        selected = random.choice(all_files)
        print(f"  ✓ Using local music: {selected.name}")
        return selected

    return None


def save_to_cache(track: Dict, local_path: Path):
    """Сохранить информацию о треке в кеш."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    cache = {"tracks": []}
    if MUSIC_CACHE_FILE.exists():
        with open(MUSIC_CACHE_FILE, "r") as f:
            cache = json.load(f)

    cache["tracks"].append({
        "id": track.get("id"),
        "title": track.get("title"),
        "duration": track.get("duration"),
        "tags": track.get("tags", ""),
        "local_path": str(local_path)
    })

    with open(MUSIC_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def get_audio_duration(audio_path: Path) -> float:
    """Получить длительность аудио файла через ffprobe."""
    import subprocess

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except:
        return 0.0


def prepare_music_for_video(
    music_path: Path,
    video_duration: float,
    output_path: Path,
    volume: float = 0.15,
    fade_in: float = 2.0,
    fade_out: float = 3.0
) -> bool:
    """
    Подготовить музыку для видео: обрезать/зациклить, добавить fade.

    Args:
        music_path: Путь к исходной музыке
        video_duration: Длительность видео
        output_path: Путь для сохранения
        volume: Громкость (0.0-1.0), 0.15 = 15%
        fade_in: Длительность fade in
        fade_out: Длительность fade out

    Returns:
        True если успешно
    """
    import subprocess

    music_duration = get_audio_duration(music_path)

    if music_duration <= 0:
        print(f"Cannot get music duration: {music_path}")
        return False

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Строим filter_complex
    filters = []

    # Если музыка короче видео — зацикливаем
    if music_duration < video_duration:
        loops_needed = int(video_duration / music_duration) + 1
        # Используем aloop для зацикливания
        filters.append(f"aloop=loop={loops_needed}:size={int(music_duration * 44100)}")

    # Обрезаем до нужной длины
    # Fade in в начале
    filters.append(f"afade=t=in:st=0:d={fade_in}")

    # Fade out в конце
    fade_out_start = video_duration - fade_out
    filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")

    # Громкость
    filters.append(f"volume={volume}")

    filter_string = ",".join(filters)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(music_path),
        "-af", filter_string,
        "-t", str(video_duration),
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)

    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        return False

    return output_path.exists()


def build_music_bed(
    pool: list,
    total_duration: float,
    output_path: Path,
    volume: float = 0.12,
    crossfade: float = 2.0,
) -> bool:
    """Собирает фоновую дорожку из пула треков (house_music) на ВСЮ длину видео.

    Рандомно секвенсит 1-5 треков с кроссфейдами → лупит до total_duration → trim →
    fade in 2s / out 3s → громкость volume → стерео 44100 mp3. Не привязано к mood/таймингам.
    Фолбэк: луп одного случайного трека.
    """
    import random
    import subprocess
    import tempfile

    pool = [Path(p) for p in pool if Path(p).exists()]
    if not pool or total_duration <= 0:
        logger.warning("build_music_bed: пустой пул или нулевая длина")
        return False
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tracks = pool[:]
    random.shuffle(tracks)
    tracks = tracks[:5]

    fade_out_start = max(0.0, total_duration - 3.0)

    def _loop_fade(src: Path) -> bool:
        af = (f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start:.2f}:d=3,"
              f"volume={volume},aformat=channel_layouts=stereo:sample_rates=44100")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-stream_loop", "-1", "-i", str(src), "-af", af,
               "-t", f"{total_duration:.2f}", "-c:a", "libmp3lame", "-b:a", "160k",
               str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        return output_path.exists() and output_path.stat().st_size > 10000

    try:
        with tempfile.TemporaryDirectory() as td:
            if len(tracks) == 1:
                seq = tracks[0]
            else:
                seq = Path(td) / "seq.mp3"
                inputs = []
                for t in tracks:
                    inputs += ["-i", str(t)]
                fc, prev = "", "[0:a]"
                for i in range(1, len(tracks)):
                    out = f"[a{i}]"
                    fc += f"{prev}[{i}:a]acrossfade=d={crossfade}:c1=tri:c2=tri{out};"
                    prev = out
                fc = fc.rstrip(";")
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                                *inputs, "-filter_complex", fc, "-map", prev,
                                "-c:a", "libmp3lame", "-b:a", "192k", str(seq)],
                               check=True, capture_output=True, timeout=300)
            return _loop_fade(seq)
    except Exception as e:
        logger.warning(f"build_music_bed: кроссфейд упал ({e}); фолбэк — один трек")
        try:
            return _loop_fade(random.choice(pool))
        except Exception as e2:
            logger.error(f"build_music_bed fallback failed: {e2}")
            return False


def main():
    """CLI для тестирования."""
    import argparse

    parser = argparse.ArgumentParser(description="Music Client")
    parser.add_argument("--search", "-s", help="Search query")
    parser.add_argument("--theme", "-t", help="Theme (egypt, conspiracy, ufo, history)")
    parser.add_argument("--duration", "-d", type=float, default=300, help="Needed duration (seconds)")
    parser.add_argument("--output", "-o", default=".", help="Output directory")
    parser.add_argument("--list-local", action="store_true", help="List local music files")

    args = parser.parse_args()

    if args.list_local:
        music_dir = MUSIC_DIR
        if music_dir.exists():
            for f in music_dir.glob("*.mp3"):
                duration = get_audio_duration(f)
                print(f"  {f.name}: {duration:.1f}s")
        else:
            print("No local music found")
        return

    if args.search:
        print(f"Searching: {args.search}")
        tracks = search_music(args.search, per_page=5)
        for t in tracks:
            print(f"  {t.get('title', 'Unknown')} - {t.get('duration', 0)}s")
        return

    if args.theme:
        print(f"Getting music for theme: {args.theme}")
        result = get_music_for_theme(
            theme=args.theme,
            duration_needed=args.duration,
            output_dir=Path(args.output)
        )
        if result:
            print(f"Downloaded: {result}")
        else:
            print("No music found")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
