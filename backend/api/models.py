"""Pydantic models for the YouTube Factory API."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CreateVideoRequest(BaseModel):
    topic: str = Field(..., description="Video topic")
    lang: str = Field(..., description="Language code: de, es")
    duration_minutes: int = Field(22, ge=5, le=60, description="Target video length")
    style: str = Field("documentary", description="Visual style")
    music_mood: str = Field("auto", description="Background music mood")
    music_track_id: Optional[str] = Field(None, description="Manual music track ID from library")
    output_mode: str = Field("fcpxml", description='"fcpxml" (DaVinci-проект zip) | "rendered" (FFmpeg mp4)')
    tts_mode: str = Field("fal", description='"fal" (бренд-голос, ~$2/видео) | "free" (Edge, бесплатно, для тестов)')
    visual_mode: Optional[str] = Field(None, description='"pexels" сток | "stick_figure" AI-картинки. None → дефолт канала из channels.yaml')
    source_transcript: Optional[str] = Field(None, description='Транскрипт проверенного видоса-референса: пайплайн напишет ОРИГИНАЛЬНЫЙ сценарий, повторяя его структуру+реальные факты своими словами (не копия)')


class VideoResponse(BaseModel):
    task_id: str
    topic: str
    lang: str
    status: str
    current_phase: str = ""
    phase_detail: Optional[str] = None
    progress_percent: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None
    download_url: Optional[str] = None
    workspace: Optional[str] = None
    checkpoint: Optional[Dict[str, Any]] = None
    titles: Optional[List[str]] = None
    titles_ru: Optional[List[str]] = None  # русский перевод тайтлов (для понимания в библиотеке)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    # Гейт одобрения сценария
    script_score: Optional[int] = None
    script_ru: Optional[str] = None
    script_de: Optional[str] = None
    script_rubric: Optional[Dict[str, Any]] = None  # разбивка балла судьи (критерии, слабые места, вердикт)
    on_channel: bool = False  # тема уже опубликована на YouTube-канале клиента (для черновиков)
    already_built: bool = False  # по этому сценарию уже собрано видео (есть в Библиотеке) — чтобы не собирать дважды
    improve_note: Optional[str] = None  # результат последнего «Улучшить»: «улучшено 78→82» / «не удалось превзойти…»


class TopicIdea(BaseModel):
    id: str = Field("", description="Stable archive id (hash of lang+title)")
    status: str = Field("new", description="new | used")
    title_original: str = Field(..., description="Title in video language")
    title_ru: str = Field("", description="Russian translation for review")
    category: str = Field("", description="Topic category")
    hook: str = Field("", description="One-sentence hook")
    hook_ru: str = Field("", description="Hook in Russian")
    virality_score: int = Field(0, ge=0, le=100, description="Virality rating 0-100%")
    why_viral: str = Field("", description="Why this topic would perform well")
    source_video: Optional[str] = Field(None, description="Competitor video URL if found")
    source_views: Optional[int] = Field(None, description="Source video view count")


class ApproveScriptRequest(BaseModel):
    tts_mode: str = Field("fal", description='"fal" (бренд-голос) | "free" (Edge, тест)')
    visual_mode: Optional[str] = Field(None, description='"pexels" сток | "stick_figure" AI-картинки. None → дефолт канала из channels.yaml')
    revoice: bool = Field(False, description='Пересборка: переозвучить новым голосом (re-voice) + пересчитать тайминги; сцены/сценарий/картинки переиспользуются')
    keep_visuals: bool = Field(False, description='Переозвучка с СОХРАНЕНИЕМ картинок+музыки: только новый голос, картинки пере-таймятся под него (без регенерации)')


class TranslateVideoRequest(BaseModel):
    """Сделать ТУ ЖЕ видеоверсию на другом языке: картинки/музыка источника
    переиспользуются как есть, переводится только сценарий → новая озвучка +
    пере-тайминг тех же кадров + переведённые метаданные/превью. Мульти-язык
    почти бесплатно (см. es-channel-multilang-strategy)."""
    target_lang: str = Field(..., description='Язык новой версии (de/en/...). Должен отличаться от языка источника')
    voice_id: Optional[str] = Field(None, description='Голос целевого языка (ElevenLabs id). None → voices.yaml[target_lang].voice_id. Для de-curiosity передавай немецкий голос, чтобы не брать финанс-голос канала')
    tts_mode: str = Field("fal", description='"fal" (бренд-голос) | "free" (Edge, тест)')
    translate_metadata: bool = Field(True, description='true → перевести метаданные источника на целевой язык (сохраняет curiosity-тон, минует de=finance-конфиг). false → сгенерировать с нуля')


class TopicDiscoverRequest(BaseModel):
    num_ideas: int = Field(5, ge=1, le=30, description="Number of topic ideas")


class TopicDiscoverResponse(BaseModel):
    ideas: List[TopicIdea]
    pattern_analysis: Optional[str] = None
    channel_name: str = ""
    niche: str = ""
    recent_topics: List[str] = []


class ChannelInfo(BaseModel):
    lang: str
    name: str
    niche: str
    description: str
    voice_id: str
    style: str
    duration_minutes: int
    history_window: int
    recent_topics: List[str] = []
    total_videos: int = 0


class MusicTrack(BaseModel):
    id: str
    name: str
    path: str
    mood: str
    volume: float
    bpm: Optional[int] = None
    duration_sec: Optional[int] = None


class MetadataResponse(BaseModel):
    titles: List[str] = Field(..., description="3 viral title options")
    titles_ru: List[str] = Field(default_factory=list, description="Russian translations")
    description: str = ""
    tags: List[str] = []


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    model: str
    lang: str


class ThemeInfo(BaseModel):
    key: str
    description: str
    weight: float
    example_topics: List[str] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    commit: str = ""  # git SHA деплоя (Railway: RAILWAY_GIT_COMMIT_SHA)
