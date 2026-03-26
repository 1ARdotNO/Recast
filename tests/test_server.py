"""Tests for FastAPI server."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from recast.server import app, _global_config


@pytest.fixture(autouse=True)
def setup_shows(tmp_path, monkeypatch):
    """Set up a test shows directory."""
    shows_dir = tmp_path / "shows"
    shows_dir.mkdir()

    show1 = shows_dir / "testshow"
    show1.mkdir()
    (show1 / "incoming").mkdir()
    (show1 / "episodes").mkdir()
    (show1 / ".recast" / "jobs").mkdir(parents=True)
    (show1 / "show.toml").write_text(
        '[show]\nname = "Test Show"\ndescription = "A test"\n'
        'author = "Author"\nlanguage = "no"\n'
    )

    # Override global config
    import recast.server
    recast.server._global_config = {
        "shows_dir": str(shows_dir),
        "log_level": "info",
        "log_file": "",
        "ui_host": "127.0.0.1",
        "ui_port": 8765,
        "auto_open_browser": False,
        "hf_token": "",
    }

    return shows_dir


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestAPI:
    @pytest.mark.anyio
    async def test_list_shows(self, client):
        resp = await client.get("/api/shows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Show"

    @pytest.mark.anyio
    async def test_list_jobs_empty(self, client):
        resp = await client.get("/api/shows/testshow/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_show_settings(self, client):
        resp = await client.get("/api/shows/testshow/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Show"
        assert data["language"] == "no"

    @pytest.mark.anyio
    async def test_show_not_found(self, client):
        resp = await client.get("/api/shows/nonexistent/jobs")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_ffmpeg_check(self, client):
        resp = await client.get("/api/test/ffmpeg")
        assert resp.status_code == 200
        assert resp.json()["available"] is True

    @pytest.mark.anyio
    async def test_ollama_check(self, client):
        resp = await client.get("/api/test/ollama")
        assert resp.status_code == 200
        # May fail if Ollama not running, but should not error
        assert "status" in resp.json()

    @pytest.mark.anyio
    async def test_job_not_found(self, client):
        resp = await client.get("/api/shows/testshow/jobs/fake-id")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_cutlist_not_found(self, client):
        resp = await client.get("/api/shows/testshow/jobs/fake-id/cutlist")
        assert resp.status_code == 404
