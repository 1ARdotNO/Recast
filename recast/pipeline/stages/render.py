"""Stage 6 — Render: Audio stitching with ffmpeg."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import structlog

from recast.models.cut import CutList

logger = structlog.get_logger()


def _extract_segment(
    input_path: Path, start: float, end: float, output_path: Path,
) -> None:
    """Extract a segment from an audio file."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-ss", str(start),
            "-to", str(end),
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        capture_output=True, text=True, check=True,
    )


def _concat_hard_cut(segment_files: list[Path], output_path: Path) -> None:
    """Concatenate audio files with hard cuts."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for seg_file in segment_files:
            f.write(f"file '{seg_file}'\n")
        concat_list = f.name

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        capture_output=True, text=True, check=True,
    )
    Path(concat_list).unlink(missing_ok=True)


def _concat_with_silence(
    segment_files: list[Path], output_path: Path, silence_ms: int = 500,
) -> None:
    """Concatenate with silence gaps between segments."""
    if not segment_files:
        return

    # Build ffmpeg filter for inserting silence
    inputs = []
    silence_s = silence_ms / 1000.0

    for i, seg_file in enumerate(segment_files):
        inputs.extend(["-i", str(seg_file)])

    if len(segment_files) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(segment_files[0]),
             "-c:a", "pcm_s16le", str(output_path)],
            capture_output=True, text=True, check=True,
        )
        return

    # Use concat with silence pad
    filter_chain = ""
    for i in range(len(segment_files)):
        filter_chain += f"[{i}:a]"
        if i < len(segment_files) - 1:
            filter_chain += f"apad=pad_dur={silence_s},"
            filter_chain += "atrim=end_sample=99999999,"

    # Simpler approach: add silence to each segment then concat
    with tempfile.TemporaryDirectory() as tmpdir:
        padded_files = []
        for i, seg_file in enumerate(segment_files):
            padded = Path(tmpdir) / f"padded_{i}.wav"
            if i < len(segment_files) - 1:
                # Add silence at end
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(seg_file),
                        "-af", f"apad=pad_dur={silence_s}",
                        "-c:a", "pcm_s16le",
                        str(padded),
                    ],
                    capture_output=True, text=True, check=True,
                )
            else:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(seg_file),
                        "-c:a", "pcm_s16le",
                        str(padded),
                    ],
                    capture_output=True, text=True, check=True,
                )
            padded_files.append(padded)

        _concat_hard_cut(padded_files, output_path)


def _concat_with_crossfade(
    segment_files: list[Path], output_path: Path, crossfade_ms: int = 300,
) -> None:
    """Concatenate with crossfade between segments."""
    if not segment_files:
        return

    if len(segment_files) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(segment_files[0]),
             "-c:a", "pcm_s16le", str(output_path)],
            capture_output=True, text=True, check=True,
        )
        return

    crossfade_s = crossfade_ms / 1000.0

    # Build complex filter for acrossfade
    inputs = []
    for seg_file in segment_files:
        inputs.extend(["-i", str(seg_file)])

    # Chain crossfades: [0][1]acrossfade -> [tmp1]; [tmp1][2]acrossfade -> [tmp2] ...
    filter_parts = []
    prev = "[0:a]"
    for i in range(1, len(segment_files)):
        curr = f"[{i}:a]"
        out_label = f"[cf{i}]" if i < len(segment_files) - 1 else "[out]"
        filter_parts.append(
            f"{prev}{curr}acrossfade=d={crossfade_s}:c1=tri:c2=tri{out_label}"
        )
        prev = out_label

    filter_str = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_str,
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]

    subprocess.run(cmd, capture_output=True, text=True, check=True)


def render(
    wav_path: Path,
    cutlist: CutList,
    output_dir: Path,
    join_mode: str = "crossfade",
    crossfade_duration_ms: int = 300,
    silence_duration_ms: int = 500,
    audio_format: str = "mp3",
    audio_bitrate: str = "192k",
) -> Path:
    """Render the final episode audio from the cut list.

    Returns the path to the rendered output file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"episode_audio.{audio_format}"
    tmp_wav = output_dir / "episode_rendered.wav"

    logger.info(
        "render.start",
        join_mode=join_mode,
        n_keep=len(cutlist.keep_segments),
    )

    keep_segments = sorted(cutlist.keep_segments, key=lambda d: d.start)

    if not keep_segments:
        logger.warning("render.no_segments")
        # Create empty audio
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-t", "1",
                "-b:a", audio_bitrate,
                str(output_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return output_path

    # Extract each keep segment
    with tempfile.TemporaryDirectory() as tmpdir:
        segment_files: list[Path] = []
        for i, seg in enumerate(keep_segments):
            seg_path = Path(tmpdir) / f"seg_{i:04d}.wav"
            _extract_segment(wav_path, seg.start, seg.end, seg_path)
            segment_files.append(seg_path)

        # Join segments
        if join_mode == "crossfade":
            _concat_with_crossfade(
                segment_files, tmp_wav, crossfade_duration_ms,
            )
        elif join_mode == "silence":
            _concat_with_silence(
                segment_files, tmp_wav, silence_duration_ms,
            )
        else:  # hard_cut
            _concat_hard_cut(segment_files, tmp_wav)

    # Encode to final format
    if audio_format == "wav":
        tmp_wav.rename(output_path)
    else:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(tmp_wav),
                "-b:a", audio_bitrate,
                str(output_path),
            ],
            capture_output=True, text=True, check=True,
        )
        tmp_wav.unlink(missing_ok=True)

    logger.info("render.done", output=str(output_path))
    return output_path
