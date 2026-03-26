"""End-to-end integration tests."""

import json
import subprocess
import time
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from typer.testing import CliRunner

from recast.cli import app as cli_app
from recast.config import load_show_config
from recast.models.job import JobStatus
from recast.queue import JobQueue


runner = CliRunner()


@pytest.fixture
def e2e_show(tmp_path):
    """Create a full show setup for E2E testing."""
    show = tmp_path / "e2e_show"
    show.mkdir()
    (show / "incoming").mkdir()
    (show / "episodes").mkdir()
    (show / "show.toml").write_text("""\
[show]
name = "E2E Test Show"
description = "End-to-end test show"
author = "Test"
language = "no"

[pipeline]
whisper_model = "NbAiLab/nb-whisper-small"
join_mode = "hard_cut"

[publishing]
auto_publish = false

[publishing.rss]
enabled = false
""")
    return show


@pytest.fixture
def e2e_audio(tmp_path):
    """Create a ~10 second test WAV with mixed content."""
    wav = tmp_path / "test_broadcast.wav"
    # 3s silence + 4s tone + 3s silence = 10s
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "3",
            "-filter_complex",
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[s1];"
            "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[t1];"
            "[2:a]aformat=sample_rates=44100:channel_layouts=stereo[s2];"
            "[s1][t1][s2]concat=n=3:v=0:a=1",
            str(wav),
        ],
        capture_output=True, text=True, check=True,
    )
    return wav


@pytest.fixture
def mock_ai():
    """Mock both Whisper and Ollama for E2E tests."""
    with patch("faster_whisper.WhisperModel") as MockWhisper, \
         patch("ollama.Client") as MockOllama:

        # Whisper mock
        whisper = MagicMock()
        MockWhisper.return_value = whisper

        class MockSeg:
            start = 0.0
            end = 4.0
            text = "Velkommen til sendingen. I dag snakker vi om nyheter."
            words = []

        class MockInfo:
            language = "no"
            language_probability = 0.95
            duration = 10.0

        whisper.transcribe.return_value = (iter([MockSeg()]), MockInfo())

        # Ollama mock
        ollama_client = MagicMock()
        MockOllama.return_value = ollama_client
        ollama_client.chat.side_effect = [
            # LLM pass: no cuts
            {"message": {"content": "[]"}},
            # Metadata
            {"message": {"content": json.dumps({
                "title": "Nyheter i dag",
                "description": "En oversikt over dagens nyheter.",
                "chapters": [
                    {"title": "Intro", "start_time": 0.0},
                    {"title": "Nyheter", "start_time": 3.0},
                ],
            })}},
        ]

        yield


class TestFullPipeline:
    def test_cli_run(self, e2e_show, e2e_audio, mock_ai):
        """Test full pipeline via CLI run command."""
        result = runner.invoke(cli_app, [
            "run", str(e2e_show), str(e2e_audio),
        ])
        assert result.exit_code == 0, result.output
        assert "Nyheter i dag" in result.output

        # Verify artifacts
        queue = JobQueue(e2e_show / ".recast" / "recast.db")
        jobs = queue.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.DONE

        episode = queue.get_episode(jobs[0].id)
        assert episode is not None
        assert episode.title == "Nyheter i dag"

    def test_cli_status(self, e2e_show, e2e_audio, mock_ai):
        """Test status command after processing."""
        runner.invoke(cli_app, ["run", str(e2e_show), str(e2e_audio)])
        result = runner.invoke(cli_app, ["status", str(e2e_show)])
        assert result.exit_code == 0
        assert "done" in result.output.lower() or "Done" in result.output

    def test_cli_dry_run(self, e2e_show, e2e_audio, mock_ai):
        """Test dry-run mode."""
        result = runner.invoke(cli_app, [
            "run", str(e2e_show), str(e2e_audio), "--dry-run",
        ])
        assert result.exit_code == 0

    def test_pipeline_resume(self, e2e_show, e2e_audio, mock_ai):
        """Test pipeline resume after interruption."""
        from recast.pipeline.runner import PipelineRunner
        from recast.pipeline.stages.normalize import normalize

        config = load_show_config(e2e_show)
        queue = JobQueue(config.db_path)
        job = queue.create_job("test.wav", str(e2e_audio))

        # Pre-run normalize
        job_dir = config.job_dir(job.id)
        normalize(str(e2e_audio), job_dir)

        # Run full pipeline (should resume from segment)
        runner_obj = PipelineRunner(config, queue)
        episode = runner_obj.run(job)
        assert episode is not None
        assert episode.title == "Nyheter i dag"

    def test_review_mode(self, e2e_show, e2e_audio, mock_ai):
        """Test review mode pauses at reconcile."""
        # Enable review mode — replace existing publishing section
        (e2e_show / "show.toml").write_text("""\
[show]
name = "E2E Test Show"

[pipeline]
join_mode = "hard_cut"

[publishing]
auto_publish = false
review_mode = true
""")

        result = runner.invoke(cli_app, [
            "run", str(e2e_show), str(e2e_audio),
        ])
        assert "review" in result.output.lower()

    def test_job_artifacts(self, e2e_show, e2e_audio, mock_ai):
        """Test all expected artifacts are created."""
        from recast.pipeline.runner import PipelineRunner

        config = load_show_config(e2e_show)
        queue = JobQueue(config.db_path)
        job = queue.create_job("test.wav", str(e2e_audio))

        pipeline = PipelineRunner(config, queue)
        pipeline.run(job)

        job_dir = config.job_dir(job.id)
        assert (job_dir / "audio_normalized.wav").exists()
        assert (job_dir / "segments_pyannote.json").exists()
        assert (job_dir / "transcript.json").exists()
        assert (job_dir / "cuts_llm.json").exists()
        assert (job_dir / "cutlist_final.json").exists()
        assert (job_dir / "episode_audio.mp3").exists()
        assert (job_dir / "episode_metadata.json").exists()


class TestWatcherE2E:
    def test_watcher_detects_and_queues(self, e2e_show, e2e_audio, mock_ai):
        """Test that watcher detects files and creates jobs."""
        from recast.watcher import ShowWatcher

        config = load_show_config(e2e_show)
        detected = []

        def callback(path, cfg):
            detected.append(path)

        watcher = ShowWatcher()
        watcher.add_show(config, callback)
        watcher.start()

        try:
            # Copy audio to watch folder
            import shutil
            shutil.copy2(e2e_audio, config.watch_path / "broadcast.wav")
            time.sleep(3.5)
            assert len(detected) == 1
            assert detected[0].name == "broadcast.wav"
        finally:
            watcher.stop()


class TestServerE2E:
    @pytest.fixture(autouse=True)
    def setup_server(self, e2e_show):
        import recast.server
        shows_dir = e2e_show.parent
        recast.server._global_config = {
            "shows_dir": str(shows_dir),
            "log_level": "info",
            "log_file": "",
            "ui_host": "127.0.0.1",
            "ui_port": 8765,
            "auto_open_browser": False,
            "hf_token": "",
        }

    @pytest.fixture
    async def client(self):
        from recast.server import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    @pytest.mark.anyio
    async def test_show_listed(self, client):
        resp = await client.get("/api/shows")
        assert resp.status_code == 200
        shows = resp.json()
        assert any(s["name"] == "E2E Test Show" for s in shows)

    @pytest.mark.anyio
    async def test_settings_readable(self, client):
        resp = await client.get("/api/shows/e2e_show/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "E2E Test Show"
        assert data["join_mode"] == "hard_cut"
