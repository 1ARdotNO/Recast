"""Tests for Stage 2 — Segment."""

import json
import subprocess
from pathlib import Path

import pytest

from recast.models.cut import Segment, SegmentType
from recast.pipeline.stages.segment import (
    segment, _energy_based_vad, _merge_short_gaps,
)


@pytest.fixture
def normalized_wav(tmp_path) -> Path:
    """Create a 16kHz mono WAV with a mix of silence and tone."""
    wav_path = tmp_path / "audio_normalized.wav"
    # 2s silence + 3s tone + 2s silence + 3s tone = 10s
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "aevalsrc=0:d=2,apad=pad_dur=0[s1];"
            "sine=frequency=440:duration=3[t1];"
            "aevalsrc=0:d=2,apad=pad_dur=0[s2];"
            "sine=frequency=880:duration=3[t2];"
            "[s1][t1][s2][t2]concat=n=4:v=0:a=1",
            "-ar", "16000", "-ac", "1",
            str(wav_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return wav_path


class TestEnergyBasedVAD:
    def test_detects_speech_regions(self, normalized_wav):
        segments = _energy_based_vad(
            normalized_wav,
            energy_threshold=100.0,
            min_speech_gap_s=0.5,
        )
        assert len(segments) > 0
        # Should have some speech and some non-speech
        speech = [s for s in segments if s.type == SegmentType.SPEECH]
        non_speech = [s for s in segments if s.type == SegmentType.MUSIC]
        assert len(speech) > 0
        assert len(non_speech) > 0

    def test_all_silence(self, tmp_path):
        wav_path = tmp_path / "silence.wav"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-t", "2",
                str(wav_path),
            ],
            capture_output=True, text=True, check=True,
        )
        segments = _energy_based_vad(wav_path, energy_threshold=100.0)
        # All should be non-speech
        for s in segments:
            assert s.type == SegmentType.MUSIC


class TestMergeShortGaps:
    def test_merge_adjacent_speech(self):
        segments = [
            Segment(start=0.0, end=1.0, type=SegmentType.SPEECH),
            Segment(start=1.0, end=1.3, type=SegmentType.MUSIC),  # short gap
            Segment(start=1.3, end=3.0, type=SegmentType.SPEECH),
        ]
        merged = _merge_short_gaps(segments, min_gap_s=0.5)
        assert len(merged) == 1
        assert merged[0].type == SegmentType.SPEECH
        assert merged[0].start == 0.0
        assert merged[0].end == 3.0

    def test_keep_long_gaps(self):
        segments = [
            Segment(start=0.0, end=1.0, type=SegmentType.SPEECH),
            Segment(start=1.0, end=3.0, type=SegmentType.MUSIC),  # long gap
            Segment(start=3.0, end=5.0, type=SegmentType.SPEECH),
        ]
        merged = _merge_short_gaps(segments, min_gap_s=0.5)
        assert len(merged) == 3

    def test_empty(self):
        assert _merge_short_gaps([], 0.5) == []


class TestSegment:
    def test_produces_output_file(self, normalized_wav, tmp_path):
        output_dir = tmp_path / "job"
        segments = segment(normalized_wav, output_dir)
        output_file = output_dir / "segments_pyannote.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert isinstance(data, list)
        assert len(data) == len(segments)

    def test_segments_roundtrip(self, normalized_wav, tmp_path):
        output_dir = tmp_path / "job"
        segments = segment(normalized_wav, output_dir)
        output_file = output_dir / "segments_pyannote.json"
        data = json.loads(output_file.read_text())
        restored = [Segment.from_dict(d) for d in data]
        assert len(restored) == len(segments)
        for orig, rest in zip(segments, restored):
            assert orig.start == rest.start
            assert orig.end == rest.end
            assert orig.type == rest.type
