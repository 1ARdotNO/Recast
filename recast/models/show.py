"""Show config model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShowConfig:
    # [show]
    name: str = "Untitled Show"
    description: str = ""
    author: str = ""
    language: str = "no"
    cover_image: str = ""

    # [input]
    watch_folder: str = "incoming"
    file_patterns: list[str] = field(
        default_factory=lambda: ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]
    )

    # [output]
    output_folder: str = "episodes"
    audio_format: str = "mp3"
    audio_bitrate: str = "192k"

    # [pipeline]
    whisper_model: str = "NbAiLab/nb-whisper-small"
    whisper_language: str = "no"
    ollama_model: str = "gemma3:12b"
    ollama_base_url: str = "http://localhost:11434"
    join_mode: str = "crossfade"  # crossfade | hard_cut | silence
    crossfade_duration_ms: int = 300
    silence_duration_ms: int = 500
    cut_pad_ms: int = 300
    min_speech_gap_s: float = 0.5
    min_keep_duration_s: float = 2.0
    llm_confidence_threshold: float = 0.6
    llm_prompt_template: str | None = None  # path to custom prompt file

    # [publishing]
    auto_publish: bool = True
    review_mode: bool = False

    # [publishing.rss]
    rss_enabled: bool = True
    feed_file: str = "feed.xml"
    feed_base_url: str = ""

    # [publishing.apple_podcasts]
    apple_podcasts_enabled: bool = True

    # [publishing.rss.itunes]
    itunes_category: str = "News"
    itunes_subcategory: str = ""
    itunes_explicit: bool = False

    # Runtime: resolved absolute path to the show folder
    show_folder: Path = field(default_factory=lambda: Path("."))

    def resolve_path(self, relative: str) -> Path:
        return self.show_folder / relative

    @property
    def watch_path(self) -> Path:
        return self.resolve_path(self.watch_folder)

    @property
    def output_path(self) -> Path:
        return self.resolve_path(self.output_folder)

    @property
    def recast_dir(self) -> Path:
        return self.resolve_path(".recast")

    @property
    def db_path(self) -> Path:
        return self.recast_dir / "recast.db"

    @property
    def jobs_dir(self) -> Path:
        return self.recast_dir / "jobs"

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id
