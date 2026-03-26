"""Tests for config loading and validation."""

from pathlib import Path

import pytest

from recast.config import load_show_config, load_global_config, discover_shows


MINIMAL_SHOW_TOML = """\
[show]
name = "Test Show"
"""

FULL_SHOW_TOML = """\
[show]
name = "Morgennytt"
description = "News show"
author = "NRK P2"
language = "no"
cover_image = "cover.jpg"

[input]
watch_folder = "incoming"
file_patterns = ["*.mp3", "*.wav"]

[output]
folder = "episodes"
audio_format = "mp3"
audio_bitrate = "192k"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-large"
language = "no"
ollama_model = "gemma3:12b"
ollama_base_url = "http://localhost:11434"
join_mode = "crossfade"
crossfade_duration_ms = 300
silence_duration_ms = 500
cut_pad_ms = 300
min_speech_gap_s = 0.5
min_keep_duration_s = 2.0
llm_confidence_threshold = 0.6

[publishing]
auto_publish = true

[publishing.rss]
enabled = true
feed_file = "feed.xml"
feed_base_url = "https://example.com/recast"

[publishing.apple_podcasts]
enabled = true

[publishing.rss.itunes]
category = "News"
subcategory = "Daily News"
explicit = false
"""

GLOBAL_CONFIG_TOML = """\
[recast]
shows_dir = "./my_shows"
log_level = "debug"
log_file = "custom.log"

[ui]
host = "0.0.0.0"
port = 9000
auto_open_browser = false

[models]
hf_token = "hf_test123"
"""


class TestLoadShowConfig:
    def test_minimal(self, tmp_path):
        (tmp_path / "show.toml").write_text(MINIMAL_SHOW_TOML)
        cfg = load_show_config(tmp_path)
        assert cfg.name == "Test Show"
        assert cfg.language == "no"
        assert cfg.whisper_model == "NbAiLab/nb-whisper-small"

    def test_full(self, tmp_path):
        (tmp_path / "show.toml").write_text(FULL_SHOW_TOML)
        cfg = load_show_config(tmp_path)
        assert cfg.name == "Morgennytt"
        assert cfg.author == "NRK P2"
        assert cfg.whisper_model == "NbAiLab/nb-whisper-large"
        assert cfg.ollama_model == "gemma3:12b"
        assert cfg.join_mode == "crossfade"
        assert cfg.crossfade_duration_ms == 300
        assert cfg.rss_enabled is True
        assert cfg.feed_base_url == "https://example.com/recast"
        assert cfg.itunes_category == "News"
        assert cfg.itunes_subcategory == "Daily News"
        assert cfg.apple_podcasts_enabled is True

    def test_missing_config(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_show_config(tmp_path)

    def test_custom_config_path(self, tmp_path):
        custom = tmp_path / "custom.toml"
        custom.write_text(MINIMAL_SHOW_TOML)
        cfg = load_show_config(tmp_path, config_path=custom)
        assert cfg.name == "Test Show"

    def test_invalid_join_mode(self, tmp_path):
        toml = '[show]\nname="T"\n[pipeline]\njoin_mode="invalid"'
        (tmp_path / "show.toml").write_text(toml)
        with pytest.raises(ValueError, match="Invalid join_mode"):
            load_show_config(tmp_path)

    def test_defaults_preserved(self, tmp_path):
        (tmp_path / "show.toml").write_text(MINIMAL_SHOW_TOML)
        cfg = load_show_config(tmp_path)
        assert cfg.auto_publish is True
        assert cfg.audio_format == "mp3"
        assert cfg.audio_bitrate == "192k"
        assert cfg.min_keep_duration_s == 2.0
        assert cfg.cut_pad_ms == 300

    def test_show_folder_resolved(self, tmp_path):
        (tmp_path / "show.toml").write_text(MINIMAL_SHOW_TOML)
        cfg = load_show_config(tmp_path)
        assert cfg.show_folder == tmp_path.resolve()

    def test_llm_prompt_template(self, tmp_path):
        toml = '[show]\nname="T"\n[pipeline.llm_prompt]\ntemplate_file="my_prompt.txt"'
        (tmp_path / "show.toml").write_text(toml)
        cfg = load_show_config(tmp_path)
        assert cfg.llm_prompt_template == "my_prompt.txt"

    def test_review_mode(self, tmp_path):
        toml = '[show]\nname="T"\n[publishing]\nreview_mode = true'
        (tmp_path / "show.toml").write_text(toml)
        cfg = load_show_config(tmp_path)
        assert cfg.review_mode is True


class TestLoadGlobalConfig:
    def test_defaults_when_missing(self):
        cfg = load_global_config(Path("/nonexistent/path.toml"))
        assert cfg["shows_dir"] == "./shows"
        assert cfg["log_level"] == "info"
        assert cfg["ui_port"] == 8765

    def test_full(self, tmp_path):
        (tmp_path / "recast_config.toml").write_text(GLOBAL_CONFIG_TOML)
        cfg = load_global_config(tmp_path / "recast_config.toml")
        assert cfg["shows_dir"] == "./my_shows"
        assert cfg["log_level"] == "debug"
        assert cfg["ui_host"] == "0.0.0.0"
        assert cfg["ui_port"] == 9000
        assert cfg["hf_token"] == "hf_test123"
        assert cfg["auto_open_browser"] is False


class TestDiscoverShows:
    def test_finds_shows(self, tmp_path):
        (tmp_path / "show1").mkdir()
        (tmp_path / "show1" / "show.toml").write_text(MINIMAL_SHOW_TOML)
        (tmp_path / "show2").mkdir()
        (tmp_path / "show2" / "show.toml").write_text(MINIMAL_SHOW_TOML)
        (tmp_path / "not_a_show").mkdir()  # no show.toml

        shows = discover_shows(tmp_path)
        assert len(shows) == 2

    def test_empty(self, tmp_path):
        shows = discover_shows(tmp_path)
        assert shows == []

    def test_nonexistent_dir(self):
        shows = discover_shows(Path("/nonexistent"))
        assert shows == []
