"""Tests for Stage 1 — Normalize."""

import json
import subprocess

import pytest

from recast.pipeline.stages.normalize import normalize, get_audio_duration


class TestGetAudioDuration:
    def test_duration(self, test_audio):
        dur = get_audio_duration(str(test_audio))
        assert 4.5 < dur < 5.5  # ~5 seconds

    def test_invalid_file(self, tmp_path):
        fake = tmp_path / "fake.wav"
        fake.write_text("not audio")
        with pytest.raises(subprocess.CalledProcessError):
            get_audio_duration(str(fake))


class TestNormalize:
    def test_output_exists(self, test_audio, tmp_path):
        output_dir = tmp_path / "job_output"
        path, dur = normalize(str(test_audio), output_dir)
        assert path.exists()
        assert path.name == "audio_normalized.wav"

    def test_output_is_16khz_mono(self, test_audio, tmp_path):
        output_dir = tmp_path / "job_output"
        path, _ = normalize(str(test_audio), output_dir)
        # Check with ffprobe
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(result.stdout)["streams"]
        audio = streams[0]
        assert audio["sample_rate"] == "16000"
        assert audio["channels"] == 1

    def test_duration_returned(self, test_audio, tmp_path):
        output_dir = tmp_path / "job_output"
        _, dur = normalize(str(test_audio), output_dir)
        assert 4.5 < dur < 5.5

    def test_mp3_input(self, test_audio_mp3, tmp_path):
        output_dir = tmp_path / "job_output"
        path, dur = normalize(str(test_audio_mp3), output_dir)
        assert path.exists()
        assert dur > 4.0

    def test_original_not_modified(self, test_audio, tmp_path):
        original_size = test_audio.stat().st_size
        output_dir = tmp_path / "job_output"
        normalize(str(test_audio), output_dir)
        assert test_audio.stat().st_size == original_size
