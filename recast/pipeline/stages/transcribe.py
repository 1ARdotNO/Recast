"""Stage 3 — Transcribe: ASR using faster-whisper with NB-Whisper models."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from recast.models.cut import Segment, SegmentType

logger = structlog.get_logger()


def _get_device() -> str:
    """Auto-detect best available device."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "auto"  # faster-whisper handles MPS via auto
    except ImportError:
        pass
    return "cpu"


def _get_compute_type(device: str) -> str:
    """Get appropriate compute type for device."""
    if device == "cuda":
        return "float16"
    return "int8"


def transcribe(
    wav_path: Path,
    output_dir: Path,
    speech_segments: list[Segment] | None = None,
    model_name: str = "NbAiLab/nb-whisper-small",
    language: str = "no",
) -> dict:
    """Transcribe audio using faster-whisper with the given model.

    Only transcribes speech segments if provided.
    Returns transcript data with word-level timestamps.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "transcript.json"

    logger.info(
        "transcribe.start",
        model=model_name, language=language, input=str(wav_path),
    )

    device = _get_device()
    compute_type = _get_compute_type(device)

    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    # Build list of speech-only regions to transcribe
    speech_only = None
    if speech_segments:
        speech_only = [
            s for s in speech_segments if s.type == SegmentType.SPEECH
        ]

    # Transcribe
    all_segments = []

    if speech_only:
        # Transcribe only speech regions using clip_timestamps
        clip_timestamps = []
        for seg in speech_only:
            clip_timestamps.extend([seg.start, seg.end])

        segments_iter, info = model.transcribe(
            str(wav_path),
            language=language,
            word_timestamps=True,
            clip_timestamps=clip_timestamps,
        )
    else:
        segments_iter, info = model.transcribe(
            str(wav_path),
            language=language,
            word_timestamps=True,
        )

    for seg in segments_iter:
        seg_data = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "words": [],
        }
        if seg.words:
            for w in seg.words:
                seg_data["words"].append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                })
        all_segments.append(seg_data)

    transcript = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": all_segments,
    }

    output_path.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

    logger.info(
        "transcribe.done",
        n_segments=len(all_segments),
        language=info.language,
        duration=info.duration,
    )

    return transcript
