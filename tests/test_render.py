"""Tests for Stage 6 — Render."""

import json
import subprocess
from pathlib import Path

import pytest

from recast.models.cut import CutList, CutDecision
from recast.pipeline.stages.render import render


@pytest.fixture
def ten_second_wav(tmp_path) -> Path:
    """Create a 10-second WAV with varying tones."""
    wav = tmp_path / "audio_normalized.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "sine=frequency=440:duration=5",
            "-f", "lavfi", "-i",
            "sine=frequency=880:duration=5",
            "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
            "-ar", "16000", "-ac", "1",
            str(wav),
        ],
        capture_output=True, text=True, check=True,
    )
    return wav


@pytest.fixture
def simple_cutlist() -> CutList:
    """CutList keeping first 3s and last 3s, removing 4-7s."""
    return CutList(
        decisions=[
            CutDecision(start=0.0, end=3.0, keep=True, reason="speech"),
            CutDecision(start=3.0, end=7.0, keep=False, reason="music"),
            CutDecision(start=7.0, end=10.0, keep=True, reason="speech"),
        ],
        total_duration=10.0,
    )


class TestRender:
    def test_hard_cut(self, ten_second_wav, simple_cutlist, tmp_path):
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, simple_cutlist, output_dir,
            join_mode="hard_cut", audio_format="wav",
        )
        assert path.exists()
        # Output should be ~6s (3s + 3s)
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, check=True,
        )
        dur = float(json.loads(result.stdout)["format"]["duration"])
        assert 5.0 < dur < 7.0

    def test_crossfade(self, ten_second_wav, simple_cutlist, tmp_path):
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, simple_cutlist, output_dir,
            join_mode="crossfade", crossfade_duration_ms=300,
            audio_format="wav",
        )
        assert path.exists()

    def test_silence(self, ten_second_wav, simple_cutlist, tmp_path):
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, simple_cutlist, output_dir,
            join_mode="silence", silence_duration_ms=500,
            audio_format="wav",
        )
        assert path.exists()

    def test_mp3_output(self, ten_second_wav, simple_cutlist, tmp_path):
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, simple_cutlist, output_dir,
            join_mode="hard_cut", audio_format="mp3", audio_bitrate="128k",
        )
        assert path.exists()
        assert path.suffix == ".mp3"

    def test_single_segment(self, ten_second_wav, tmp_path):
        cutlist = CutList(
            decisions=[CutDecision(start=0.0, end=5.0, keep=True)],
            total_duration=10.0,
        )
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, cutlist, output_dir,
            join_mode="crossfade", audio_format="wav",
        )
        assert path.exists()

    def test_no_segments(self, ten_second_wav, tmp_path):
        cutlist = CutList(decisions=[], total_duration=10.0)
        output_dir = tmp_path / "job"
        path = render(
            ten_second_wav, cutlist, output_dir,
            join_mode="hard_cut", audio_format="mp3",
        )
        assert path.exists()
