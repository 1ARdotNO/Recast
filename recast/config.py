"""TOML config loader and validation."""

from __future__ import annotations

import tomllib
from pathlib import Path

from recast.models.show import ShowConfig


def load_show_config(show_folder: Path, config_path: Path | None = None) -> ShowConfig:
    """Load a show.toml from the given show folder."""
    if config_path is None:
        config_path = show_folder / "show.toml"

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    cfg = ShowConfig(show_folder=show_folder.resolve())

    # [show]
    show = raw.get("show", {})
    if "name" in show:
        cfg.name = show["name"]
    if "description" in show:
        cfg.description = show["description"]
    if "author" in show:
        cfg.author = show["author"]
    if "language" in show:
        cfg.language = show["language"]
    if "cover_image" in show:
        cfg.cover_image = show["cover_image"]

    # [input]
    inp = raw.get("input", {})
    if "watch_folder" in inp:
        cfg.watch_folder = inp["watch_folder"]
    if "file_patterns" in inp:
        cfg.file_patterns = inp["file_patterns"]

    # [output]
    out = raw.get("output", {})
    if "folder" in out:
        cfg.output_folder = out["folder"]
    if "audio_format" in out:
        cfg.audio_format = out["audio_format"]
    if "audio_bitrate" in out:
        cfg.audio_bitrate = out["audio_bitrate"]

    # [pipeline]
    pipe = raw.get("pipeline", {})
    if "whisper_model" in pipe:
        cfg.whisper_model = pipe["whisper_model"]
    if "language" in pipe:
        cfg.whisper_language = pipe["language"]
    if "ollama_model" in pipe:
        cfg.ollama_model = pipe["ollama_model"]
    if "ollama_base_url" in pipe:
        cfg.ollama_base_url = pipe["ollama_base_url"]
    if "join_mode" in pipe:
        if pipe["join_mode"] not in ("crossfade", "hard_cut", "silence"):
            raise ValueError(
                f"Invalid join_mode: {pipe['join_mode']}. "
                "Must be crossfade, hard_cut, or silence."
            )
        cfg.join_mode = pipe["join_mode"]
    if "crossfade_duration_ms" in pipe:
        cfg.crossfade_duration_ms = int(pipe["crossfade_duration_ms"])
    if "silence_duration_ms" in pipe:
        cfg.silence_duration_ms = int(pipe["silence_duration_ms"])
    if "cut_pad_ms" in pipe:
        cfg.cut_pad_ms = int(pipe["cut_pad_ms"])
    if "min_speech_gap_s" in pipe:
        cfg.min_speech_gap_s = float(pipe["min_speech_gap_s"])
    if "min_keep_duration_s" in pipe:
        cfg.min_keep_duration_s = float(pipe["min_keep_duration_s"])
    if "llm_confidence_threshold" in pipe:
        cfg.llm_confidence_threshold = float(pipe["llm_confidence_threshold"])

    # [pipeline.llm_prompt]
    llm_prompt = pipe.get("llm_prompt", {})
    if "template_file" in llm_prompt:
        cfg.llm_prompt_template = llm_prompt["template_file"]

    # [publishing]
    pub = raw.get("publishing", {})
    if "auto_publish" in pub:
        cfg.auto_publish = pub["auto_publish"]
    if "review_mode" in pub:
        cfg.review_mode = pub["review_mode"]

    # [publishing.rss]
    rss = pub.get("rss", {})
    if "enabled" in rss:
        cfg.rss_enabled = rss["enabled"]
    if "feed_file" in rss:
        cfg.feed_file = rss["feed_file"]
    if "feed_base_url" in rss:
        cfg.feed_base_url = rss["feed_base_url"]

    # [publishing.apple_podcasts]
    apple = pub.get("apple_podcasts", {})
    if "enabled" in apple:
        cfg.apple_podcasts_enabled = apple["enabled"]

    # [publishing.rss.itunes]
    itunes = rss.get("itunes", {})
    if "category" in itunes:
        cfg.itunes_category = itunes["category"]
    if "subcategory" in itunes:
        cfg.itunes_subcategory = itunes["subcategory"]
    if "explicit" in itunes:
        cfg.itunes_explicit = itunes["explicit"]

    return cfg


def load_global_config(config_path: Path | None = None) -> dict:
    """Load the global recast_config.toml."""
    if config_path is None:
        config_path = Path("recast_config.toml")

    if not config_path.exists():
        return {
            "shows_dir": "./shows",
            "log_level": "info",
            "log_file": "recast.log",
            "ui_host": "127.0.0.1",
            "ui_port": 8765,
            "auto_open_browser": True,
            "hf_token": "",
        }

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    recast = raw.get("recast", {})
    ui = raw.get("ui", {})
    models = raw.get("models", {})

    return {
        "shows_dir": recast.get("shows_dir", "./shows"),
        "log_level": recast.get("log_level", "info"),
        "log_file": recast.get("log_file", "recast.log"),
        "ui_host": ui.get("host", "127.0.0.1"),
        "ui_port": ui.get("port", 8765),
        "auto_open_browser": ui.get("auto_open_browser", True),
        "hf_token": models.get("hf_token", ""),
    }


def discover_shows(shows_dir: Path) -> list[Path]:
    """Find all show folders (directories containing show.toml)."""
    if not shows_dir.exists():
        return []
    return sorted(
        p.parent for p in shows_dir.glob("*/show.toml")
    )
