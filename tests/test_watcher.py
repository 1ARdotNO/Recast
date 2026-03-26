"""Tests for file watcher."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recast.models.show import ShowConfig
from recast.watcher import AudioFileHandler, ShowWatcher


@pytest.fixture
def show_config(tmp_path):
    show_dir = tmp_path / "show"
    show_dir.mkdir()
    (show_dir / "incoming").mkdir()
    return ShowConfig(
        name="Test Show",
        show_folder=show_dir,
        file_patterns=["*.mp3", "*.wav"],
    )


class TestAudioFileHandler:
    def test_matches_pattern(self, show_config):
        handler = AudioFileHandler(show_config, MagicMock())
        assert handler._matches_pattern(Path("test.mp3"))
        assert handler._matches_pattern(Path("test.wav"))
        assert not handler._matches_pattern(Path("test.txt"))
        assert not handler._matches_pattern(Path("test.py"))

    def test_matches_all_patterns(self, show_config):
        show_config.file_patterns = ["*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"]
        handler = AudioFileHandler(show_config, MagicMock())
        for ext in ["mp3", "wav", "m4a", "ogg", "flac"]:
            assert handler._matches_pattern(Path(f"test.{ext}"))


class TestShowWatcher:
    def test_add_show(self, show_config):
        watcher = ShowWatcher()
        callback = MagicMock()
        watcher.add_show(show_config, callback)
        assert len(watcher._handlers) == 1

    def test_start_stop(self, show_config):
        watcher = ShowWatcher()
        callback = MagicMock()
        watcher.add_show(show_config, callback)
        watcher.start()
        assert watcher.running
        watcher.stop()
        assert not watcher.running

    def test_detects_new_file(self, show_config):
        callback = MagicMock()
        watcher = ShowWatcher()
        watcher.add_show(show_config, callback)
        watcher.start()

        try:
            # Create a file in the watch folder
            test_file = show_config.watch_path / "test.mp3"
            test_file.write_bytes(b"\x00" * 100)

            # Wait for debounce + processing
            time.sleep(3.5)

            assert callback.called
            call_args = callback.call_args[0]
            assert call_args[0].name == "test.mp3"
        finally:
            watcher.stop()

    def test_ignores_non_audio(self, show_config):
        callback = MagicMock()
        watcher = ShowWatcher()
        watcher.add_show(show_config, callback)
        watcher.start()

        try:
            test_file = show_config.watch_path / "readme.txt"
            test_file.write_text("not audio")

            time.sleep(3.5)

            assert not callback.called
        finally:
            watcher.stop()
