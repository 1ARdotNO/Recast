"""Tests for Stage 7 — Metadata."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from recast.pipeline.stages.metadata import (
    metadata, _parse_metadata_response, _format_transcript, _write_id3_chapters,
)
from recast.models.episode import Chapter


SAMPLE_TRANSCRIPT = {
    "segments": [
        {"start": 0.0, "end": 30.0, "text": "I dag diskuterer vi valgkampen."},
        {"start": 30.0, "end": 60.0, "text": "Partiene er uenige om skatt."},
        {"start": 60.0, "end": 90.0, "text": "Nå over til kultur og sport."},
    ],
}


class TestFormatTranscript:
    def test_basic(self):
        text = _format_transcript(SAMPLE_TRANSCRIPT)
        assert "[0.0s]" in text
        assert "valgkampen" in text

    def test_empty(self):
        assert _format_transcript({"segments": []}) == ""


class TestParseMetadataResponse:
    def test_valid_json(self):
        response = json.dumps({
            "title": "Valgkampen 2025",
            "description": "En diskusjon om valgkampen.",
            "chapters": [
                {"title": "Intro", "start_time": 0.0},
                {"title": "Skatt", "start_time": 30.0},
            ],
        })
        result = _parse_metadata_response(response)
        assert result["title"] == "Valgkampen 2025"
        assert len(result["chapters"]) == 2

    def test_json_with_text(self):
        response = 'Here is the metadata:\n{"title": "Test", "description": "A test.", "chapters": []}\nDone.'
        result = _parse_metadata_response(response)
        assert result["title"] == "Test"

    def test_no_json(self):
        result = _parse_metadata_response("No metadata to generate.")
        assert result["title"] == ""
        assert result["chapters"] == []


class TestMetadata:
    @pytest.fixture
    def mock_ollama(self):
        with patch("ollama.Client") as MockClient:
            client = MagicMock()
            MockClient.return_value = client
            client.chat.return_value = {
                "message": {
                    "content": json.dumps({
                        "title": "Valgkampen i fokus",
                        "description": "En diskusjon om den pågående valgkampen og skattedebatten.",
                        "chapters": [
                            {"title": "Valgkamp", "start_time": 0.0},
                            {"title": "Kultur og sport", "start_time": 60.0},
                        ],
                    }),
                },
            }
            yield client

    def test_basic(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        episode = metadata(
            SAMPLE_TRANSCRIPT, output_dir,
            job_id="test-job", duration_s=90.0,
        )
        assert episode.title == "Valgkampen i fokus"
        assert len(episode.chapters) == 2
        assert episode.job_id == "test-job"

    def test_output_file(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        metadata(SAMPLE_TRANSCRIPT, output_dir, job_id="test-job")
        assert (output_dir / "episode_metadata.json").exists()

    def test_chapters(self, tmp_path, mock_ollama):
        output_dir = tmp_path / "job"
        episode = metadata(
            SAMPLE_TRANSCRIPT, output_dir, job_id="test-job",
        )
        assert episode.chapters[0].title == "Valgkamp"
        assert episode.chapters[0].start_time == 0.0
        assert episode.chapters[1].start_time == 60.0


class TestWriteID3Chapters:
    def test_writes_chapters(self, tmp_path):
        import subprocess
        # Create a real MP3 to test ID3 writing
        mp3 = tmp_path / "test.mp3"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                "-b:a", "128k", str(mp3),
            ],
            capture_output=True, text=True, check=True,
        )

        chapters = [
            Chapter(title="Intro", start_time=0.0),
            Chapter(title="Main", start_time=2.5),
        ]
        _write_id3_chapters(mp3, chapters, 5.0)

        # Verify chapters were written
        from mutagen.mp3 import MP3
        audio = MP3(str(mp3))
        assert audio.tags is not None
        # Check for CHAP frames
        chap_keys = [k for k in audio.tags.keys() if k.startswith("CHAP")]
        assert len(chap_keys) == 2
