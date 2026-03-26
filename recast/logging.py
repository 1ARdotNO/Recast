"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(
    log_level: str = "info",
    log_file: str | None = None,
    no_color: bool = False,
) -> None:
    """Configure structlog with console + file output."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure stdlib logging
    handlers: list[logging.Handler] = []

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    handlers.append(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(logging.DEBUG)
        # JSON lines for file output
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set up formatter
    if no_color:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )

    for handler in handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stderr:
            handler.setFormatter(formatter)
        elif isinstance(handler, logging.FileHandler):
            json_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=[
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                ],
            )
            handler.setFormatter(json_formatter)
