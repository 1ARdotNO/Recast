"""Shared test fixtures."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def test_audio(tmp_path) -> Path:
    """Generate a short 5-second test WAV file with a sine wave."""
    audio_path = tmp_path / "test_input.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=5",
            "-ar", "44100",
            "-ac", "2",
            str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return audio_path


@pytest.fixture
def test_audio_mp3(tmp_path, test_audio) -> Path:
    """Generate a short 5-second test MP3 file."""
    mp3_path = tmp_path / "test_input.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(test_audio),
            "-b:a", "128k",
            str(mp3_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return mp3_path


@pytest.fixture
def show_folder(tmp_path) -> Path:
    """Create a minimal show folder structure."""
    show = tmp_path / "test_show"
    show.mkdir()
    (show / "incoming").mkdir()
    (show / "episodes").mkdir()
    (show / ".recast" / "jobs").mkdir(parents=True)
    (show / "show.toml").write_text(
        '[show]\nname = "Test Show"\n'
    )
    return show
