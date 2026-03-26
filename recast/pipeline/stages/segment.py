"""Stage 2 — Segment: Speech/music detection using pyannote or energy-based fallback."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import structlog

from recast.models.cut import Segment, SegmentType

logger = structlog.get_logger()


def _rms_energy(samples: list[int]) -> float:
    """Calculate RMS energy of audio samples."""
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


def _energy_based_vad(
    wav_path: Path,
    frame_duration_s: float = 0.02,
    energy_threshold: float = 500.0,
    min_speech_gap_s: float = 0.5,
) -> list[Segment]:
    """Simple energy-based voice activity detection fallback.

    Classifies frames as speech (above threshold) or non-speech.
    """
    with wave.open(str(wav_path), "rb") as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    frame_size = int(sample_rate * frame_duration_s)
    fmt = f"<{frame_size}h"
    byte_step = frame_size * sampwidth * n_channels

    speech_frames: list[tuple[float, float, bool]] = []
    offset = 0
    frame_idx = 0

    while offset + byte_step <= len(raw):
        # Extract mono samples (take first channel if stereo)
        if n_channels == 1:
            samples = list(struct.unpack(fmt, raw[offset:offset + byte_step]))
        else:
            all_samples = struct.unpack(
                f"<{frame_size * n_channels}h",
                raw[offset:offset + byte_step],
            )
            samples = list(all_samples[::n_channels])[:frame_size]

        energy = _rms_energy(samples)
        start = frame_idx * frame_duration_s
        end = start + frame_duration_s
        is_speech = energy > energy_threshold

        speech_frames.append((start, end, is_speech))
        offset += byte_step
        frame_idx += 1

    if not speech_frames:
        return []

    # Merge consecutive frames of the same type
    segments: list[Segment] = []
    current_start = speech_frames[0][0]
    current_type = SegmentType.SPEECH if speech_frames[0][2] else SegmentType.MUSIC
    current_end = speech_frames[0][1]

    for start, end, is_speech in speech_frames[1:]:
        seg_type = SegmentType.SPEECH if is_speech else SegmentType.MUSIC
        if seg_type == current_type:
            current_end = end
        else:
            segments.append(Segment(
                start=current_start, end=current_end, type=current_type,
            ))
            current_start = start
            current_end = end
            current_type = seg_type

    segments.append(Segment(
        start=current_start, end=current_end, type=current_type,
    ))

    # Merge short gaps in speech
    merged = _merge_short_gaps(segments, min_speech_gap_s)
    return merged


def _try_pyannote_vad(
    wav_path: Path,
    hf_token: str | None = None,
    min_speech_gap_s: float = 0.5,
) -> list[Segment] | None:
    """Try to use pyannote for VAD. Returns None if not available."""
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return None

    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/segmentation-3.0",
            use_auth_token=hf_token,
        )
    except Exception as e:
        logger.warning("pyannote.unavailable", error=str(e))
        return None

    output = pipeline(str(wav_path))

    # Extract speech regions
    speech_regions = []
    for segment, _, _ in output.itertracks(yield_label=True):
        speech_regions.append((segment.start, segment.end))

    if not speech_regions:
        return []

    # Build timeline: mark everything as music, then punch speech holes
    total_duration = speech_regions[-1][1] if speech_regions else 0.0
    segments: list[Segment] = []

    prev_end = 0.0
    for start, end in sorted(speech_regions):
        if start > prev_end:
            segments.append(Segment(
                start=prev_end, end=start, type=SegmentType.MUSIC,
            ))
        segments.append(Segment(
            start=start, end=end, type=SegmentType.SPEECH,
        ))
        prev_end = end

    merged = _merge_short_gaps(segments, min_speech_gap_s)
    return merged


def _merge_short_gaps(
    segments: list[Segment],
    min_gap_s: float,
) -> list[Segment]:
    """Merge adjacent speech segments separated by silence shorter than min_gap_s."""
    if not segments:
        return []

    merged: list[Segment] = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if (
            prev.type == SegmentType.SPEECH
            and seg.type == SegmentType.SPEECH
            and (seg.start - prev.end) < min_gap_s
        ):
            # Merge: extend previous segment
            merged[-1] = Segment(
                start=prev.start, end=seg.end, type=SegmentType.SPEECH,
            )
        elif (
            prev.type == SegmentType.SPEECH
            and seg.type == SegmentType.MUSIC
            and seg.duration < min_gap_s
        ):
            # Short non-speech gap between speech — absorb into speech
            merged[-1] = Segment(
                start=prev.start, end=seg.end, type=SegmentType.SPEECH,
            )
        else:
            merged.append(seg)

    return merged


def segment(
    wav_path: Path,
    output_dir: Path,
    min_speech_gap_s: float = 0.5,
    hf_token: str | None = None,
) -> list[Segment]:
    """Run speech/music segmentation on a normalized WAV file.

    Tries pyannote first, falls back to energy-based VAD.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "segments_pyannote.json"

    logger.info("segment.start", input=str(wav_path))

    # Try pyannote first
    segments = _try_pyannote_vad(wav_path, hf_token, min_speech_gap_s)

    if segments is None:
        logger.info("segment.fallback_energy", reason="pyannote not available")
        segments = _energy_based_vad(wav_path, min_speech_gap_s=min_speech_gap_s)

    # Save output
    data = [s.to_dict() for s in segments]
    output_path.write_text(json.dumps(data, indent=2))

    logger.info(
        "segment.done",
        n_segments=len(segments),
        n_speech=sum(1 for s in segments if s.type == SegmentType.SPEECH),
        n_music=sum(1 for s in segments if s.type == SegmentType.MUSIC),
    )

    return segments
