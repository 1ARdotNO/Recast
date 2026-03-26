"""Tests for CLI commands."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from recast.cli import app, _check_ffmpeg


runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "recast" in result.output.lower() or "Radio" in result.output

    def test_run_missing_show(self, tmp_path):
        result = runner.invoke(app, ["run", str(tmp_path / "nonexistent")])
        assert result.exit_code == 2

    def test_status_missing_show(self, tmp_path):
        result = runner.invoke(app, ["status", str(tmp_path / "nonexistent")])
        assert result.exit_code == 2

    def test_status_empty(self, tmp_path):
        show = tmp_path / "show"
        show.mkdir()
        (show / "show.toml").write_text('[show]\nname = "Test"\n')
        result = runner.invoke(app, ["status", str(show)])
        assert result.exit_code == 0
        assert "No jobs" in result.output

    def test_check_ffmpeg(self):
        assert _check_ffmpeg() is True  # ffmpeg should be available in test env

    def test_run_no_files(self, tmp_path):
        show = tmp_path / "show"
        show.mkdir()
        (show / "incoming").mkdir()
        (show / "show.toml").write_text('[show]\nname = "Test"\n')
        result = runner.invoke(app, ["run", str(show)])
        assert "No files" in result.output

    def test_publish_missing_show(self, tmp_path):
        result = runner.invoke(app, [
            "publish", str(tmp_path / "nonexistent"), "fake-id",
        ])
        assert result.exit_code == 2
