"""Watchdog-based folder monitor for incoming audio files."""

from __future__ import annotations

import fnmatch
import threading
import time
from pathlib import Path
from typing import Callable

import structlog
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from recast.models.show import ShowConfig

logger = structlog.get_logger()

FileCallback = Callable[[Path, ShowConfig], None]


class AudioFileHandler(FileSystemEventHandler):
    """Handler that detects new audio files matching show patterns."""

    def __init__(
        self,
        config: ShowConfig,
        callback: FileCallback,
        debounce_s: float = 2.0,
    ):
        self.config = config
        self.callback = callback
        self.debounce_s = debounce_s
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return

        path = Path(event.src_path)
        if self._matches_pattern(path):
            with self._lock:
                self._pending[str(path)] = time.time()

            # Debounce: wait for file to finish copying
            threading.Timer(
                self.debounce_s,
                self._process_if_stable,
                args=[path],
            ).start()

    def _matches_pattern(self, path: Path) -> bool:
        """Check if file matches any of the show's file patterns."""
        for pattern in self.config.file_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def _process_if_stable(self, path: Path) -> None:
        """Process file if it hasn't been modified since we detected it."""
        with self._lock:
            if str(path) not in self._pending:
                return
            del self._pending[str(path)]

        if path.exists():
            logger.info("watcher.new_file", path=str(path), show=self.config.name)
            try:
                self.callback(path, self.config)
            except Exception as e:
                logger.error(
                    "watcher.callback_error",
                    path=str(path), error=str(e),
                )


class ShowWatcher:
    """Watches one or more show folders for incoming audio."""

    def __init__(self):
        self._observer = Observer()
        self._handlers: list[AudioFileHandler] = []
        self._running = False

    def add_show(
        self,
        config: ShowConfig,
        callback: FileCallback,
    ) -> None:
        """Register a show folder for watching."""
        watch_path = config.watch_path
        watch_path.mkdir(parents=True, exist_ok=True)

        handler = AudioFileHandler(config, callback)
        self._handlers.append(handler)
        self._observer.schedule(handler, str(watch_path), recursive=False)

        logger.info(
            "watcher.added",
            show=config.name,
            path=str(watch_path),
        )

    def start(self) -> None:
        """Start watching all registered shows."""
        self._observer.start()
        self._running = True
        logger.info("watcher.started", n_shows=len(self._handlers))

    def stop(self) -> None:
        """Stop watching."""
        self._observer.stop()
        self._observer.join()
        self._running = False
        logger.info("watcher.stopped")

    @property
    def running(self) -> bool:
        return self._running

    def wait(self) -> None:
        """Block until interrupted."""
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
