"""Tests for Stage 3 — Transcribe."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from recast.models.cut import Segment, SegmentType
from recast.pipeline.stages.transcribe import transcribe, _get_device
import json


class MockWord:
    def __init__(self, word, start, end, probability=0.9):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class MockSegment:
    def __init__(self, start, end, text, words=None):
        self.start = start
        self.end = end
        self.text = text
        self.words = words or []


class MockTranscriptionInfo:
    def __init__(self):
        self.language = "no"
        self.language_probability = 0.95
        self.duration = 5.0


@pytest.fixture
def mock_whisper():
    """Mock faster-whisper model."""
    with patch("faster_whisper.WhisperModel") as MockModel:
        model_instance = MagicMock()
        MockModel.return_value = model_instance

        segments = [
            MockSegment(
                start=0.0, end=2.5,
                text="Hei, velkommen til programmet.",
                words=[
                    MockWord("Hei,", 0.0, 0.3),
                    MockWord("velkommen", 0.4, 0.9),
                    MockWord("til", 1.0, 1.2),
                    MockWord("programmet.", 1.3, 2.5),
                ],
            ),
            MockSegment(
                start=3.0, end=5.0,
                text="Vi snakker om nyheter i dag.",
                words=[
                    MockWord("Vi", 3.0, 3.2),
                    MockWord("snakker", 3.3, 3.7),
                    MockWord("om", 3.8, 3.9),
                    MockWord("nyheter", 4.0, 4.5),
                    MockWord("i", 4.6, 4.7),
                    MockWord("dag.", 4.8, 5.0),
                ],
            ),
        ]
        info = MockTranscriptionInfo()
        model_instance.transcribe.return_value = (iter(segments), info)

        yield model_instance


class TestTranscribe:
    def test_basic(self, tmp_path, mock_whisper):
        wav = tmp_path / "audio_normalized.wav"
        wav.touch()
        output_dir = tmp_path / "job"

        result = transcribe(wav, output_dir)

        assert result["language"] == "no"
        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == "Hei, velkommen til programmet."
        assert len(result["segments"][0]["words"]) == 4

    def test_output_file_created(self, tmp_path, mock_whisper):
        wav = tmp_path / "audio_normalized.wav"
        wav.touch()
        output_dir = tmp_path / "job"

        transcribe(wav, output_dir)

        output_file = output_dir / "transcript.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "segments" in data
        assert "language" in data

    def test_with_speech_segments(self, tmp_path, mock_whisper):
        wav = tmp_path / "audio_normalized.wav"
        wav.touch()
        output_dir = tmp_path / "job"

        speech_segments = [
            Segment(start=0.0, end=2.5, type=SegmentType.SPEECH),
            Segment(start=2.5, end=4.0, type=SegmentType.MUSIC),
            Segment(start=4.0, end=5.0, type=SegmentType.SPEECH),
        ]

        transcribe(wav, output_dir, speech_segments=speech_segments)

        # Verify clip_timestamps were passed
        call_kwargs = mock_whisper.transcribe.call_args[1]
        assert "clip_timestamps" in call_kwargs
        # Should only include speech segments
        assert call_kwargs["clip_timestamps"] == [0.0, 2.5, 4.0, 5.0]

    def test_word_timestamps(self, tmp_path, mock_whisper):
        wav = tmp_path / "audio_normalized.wav"
        wav.touch()
        output_dir = tmp_path / "job"

        result = transcribe(wav, output_dir)

        words = result["segments"][0]["words"]
        assert words[0]["word"] == "Hei,"
        assert words[0]["start"] == 0.0
        assert words[0]["probability"] == 0.9


class TestGetDevice:
    def test_returns_string(self):
        device = _get_device()
        assert device in ("cpu", "cuda", "auto")
