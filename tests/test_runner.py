"""Tests for pipeline runner."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from recast.models.job import JobStatus
from recast.models.show import ShowConfig
from recast.queue import JobQueue
from recast.pipeline.runner import PipelineRunner


@pytest.fixture
def show_config(tmp_path):
    show_dir = tmp_path / "test_show"
    show_dir.mkdir()
    (show_dir / "incoming").mkdir()
    (show_dir / "episodes").mkdir()
    (show_dir / ".recast" / "jobs").mkdir(parents=True)
    return ShowConfig(show_folder=show_dir)


@pytest.fixture
def queue(show_config):
    return JobQueue(show_config.db_path)


@pytest.fixture
def test_wav(tmp_path):
    wav = tmp_path / "input.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-ar", "44100", "-ac", "2", str(wav),
        ],
        capture_output=True, text=True, check=True,
    )
    return wav


@pytest.fixture
def mock_ollama():
    with patch("ollama.Client") as MockClient:
        client = MagicMock()
        MockClient.return_value = client
        # LLM pass response
        client.chat.side_effect = [
            # llm_pass
            {"message": {"content": "[]"}},
            # metadata
            {"message": {"content": json.dumps({
                "title": "Test Episode",
                "description": "A test episode.",
                "chapters": [{"title": "Intro", "start_time": 0.0}],
            })}},
        ]
        yield client


@pytest.fixture
def mock_whisper():
    with patch("faster_whisper.WhisperModel") as MockModel:
        model = MagicMock()
        MockModel.return_value = model

        class MockSeg:
            def __init__(self):
                self.start = 0.0
                self.end = 3.0
                self.text = "Test transcript."
                self.words = []

        class MockInfo:
            language = "no"
            language_probability = 0.95
            duration = 3.0

        model.transcribe.return_value = (iter([MockSeg()]), MockInfo())
        yield model


class TestPipelineRunner:
    def test_full_pipeline(
        self, show_config, queue, test_wav, mock_ollama, mock_whisper,
    ):
        job = queue.create_job("input.wav", str(test_wav))

        runner = PipelineRunner(show_config, queue)
        episode = runner.run(job)

        assert episode is not None
        assert episode.title == "Test Episode"
        assert job.status == JobStatus.DONE

        # Check job in DB
        db_job = queue.get_job(job.id)
        assert db_job.status == JobStatus.DONE

    def test_dry_run(
        self, show_config, queue, test_wav, mock_ollama, mock_whisper,
    ):
        job = queue.create_job("input.wav", str(test_wav))

        runner = PipelineRunner(show_config, queue, dry_run=True)
        result = runner.run(job)

        assert result is None
        db_job = queue.get_job(job.id)
        assert db_job.status == JobStatus.DONE

    def test_review_mode(
        self, show_config, queue, test_wav, mock_ollama, mock_whisper,
    ):
        show_config.review_mode = True
        job = queue.create_job("input.wav", str(test_wav))

        runner = PipelineRunner(show_config, queue)
        result = runner.run(job)

        assert result is None
        db_job = queue.get_job(job.id)
        assert db_job.status == JobStatus.REVIEW

    def test_progress_callback(
        self, show_config, queue, test_wav, mock_ollama, mock_whisper,
    ):
        progress_log = []

        def callback(stage, idx, total):
            progress_log.append((stage, idx, total))

        job = queue.create_job("input.wav", str(test_wav))
        runner = PipelineRunner(
            show_config, queue, progress_callback=callback,
        )
        runner.run(job)

        assert len(progress_log) > 0
        stages_seen = [p[0] for p in progress_log]
        assert "normalize" in stages_seen
        assert "render" in stages_seen

    def test_resume_from_normalize(
        self, show_config, queue, test_wav, mock_ollama, mock_whisper,
    ):
        job = queue.create_job("input.wav", str(test_wav))
        job_dir = show_config.job_dir(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)

        # Pre-create normalize output
        from recast.pipeline.stages.normalize import normalize
        normalize(str(test_wav), job_dir)

        runner = PipelineRunner(show_config, queue)
        episode = runner.run(job)

        assert episode is not None

    def test_failure_handled(self, show_config, queue):
        job = queue.create_job("missing.wav", "/nonexistent/missing.wav")

        runner = PipelineRunner(show_config, queue)
        result = runner.run(job)

        assert result is None
        db_job = queue.get_job(job.id)
        assert db_job.status == JobStatus.FAILED
        assert db_job.error is not None
