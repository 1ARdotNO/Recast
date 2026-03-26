"""Stage 1 — Normalize: Convert audio to WAV 16kHz mono."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger()


def get_audio_duration(input_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            input_path,
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def normalize(input_path: str, output_dir: Path) -> tuple[Path, float]:
    """Convert input audio to WAV 16kHz mono.

    Returns (output_path, duration_seconds).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "audio_normalized.wav"

    logger.info("normalize.start", input=input_path, output=str(output_path))

    # Get duration before conversion
    duration = get_audio_duration(input_path)

    # Convert to WAV 16kHz mono
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        capture_output=True, text=True, check=True,
    )

    if not output_path.exists():
        raise RuntimeError(f"Normalization failed: {output_path} not created")

    logger.info("normalize.done", duration_s=duration, output=str(output_path))
    return output_path, duration
