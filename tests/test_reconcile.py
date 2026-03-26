"""Tests for Stage 5 — Reconcile."""

import json
from pathlib import Path

import pytest

from recast.models.cut import Segment, SegmentType, CutList, CutSource
from recast.pipeline.stages.reconcile import (
    reconcile, _merge_intervals, _apply_padding,
)


class TestMergeIntervals:
    def test_no_overlap(self):
        result = _merge_intervals([(0, 1), (2, 3)])
        assert result == [(0, 1), (2, 3)]

    def test_overlap(self):
        result = _merge_intervals([(0, 2), (1, 3)])
        assert result == [(0, 3)]

    def test_adjacent(self):
        result = _merge_intervals([(0, 1), (1, 2)])
        assert result == [(0, 2)]

    def test_empty(self):
        assert _merge_intervals([]) == []

    def test_unsorted(self):
        result = _merge_intervals([(2, 3), (0, 1)])
        assert result == [(0, 1), (2, 3)]


class TestApplyPadding:
    def test_basic(self):
        result = _apply_padding([(5.0, 10.0)], 0.3, 20.0)
        assert len(result) == 1
        assert result[0][0] == pytest.approx(4.7)
        assert result[0][1] == pytest.approx(10.3)

    def test_clamp_to_bounds(self):
        result = _apply_padding([(0.1, 19.9)], 0.5, 20.0)
        assert result[0][0] == 0.0
        assert result[0][1] == 20.0

    def test_merge_after_padding(self):
        result = _apply_padding([(1.0, 2.0), (2.3, 3.0)], 0.5, 10.0)
        # After padding: (0.5, 2.5) and (1.8, 3.5) → merged into (0.5, 3.5)
        assert len(result) == 1


class TestReconcile:
    def test_basic(self, tmp_path):
        segments = [
            Segment(start=0.0, end=5.0, type=SegmentType.SPEECH),
            Segment(start=5.0, end=10.0, type=SegmentType.MUSIC),
            Segment(start=10.0, end=20.0, type=SegmentType.SPEECH),
        ]
        llm_cuts = []
        output_dir = tmp_path / "job"

        cutlist = reconcile(
            segments, llm_cuts, output_dir,
            total_duration=20.0, cut_pad_ms=0,
        )

        assert len(cutlist.keep_segments) > 0
        assert len(cutlist.remove_segments) > 0

    def test_union_rule(self, tmp_path):
        """Both pyannote music AND LLM cuts should be removed."""
        segments = [
            Segment(start=0.0, end=5.0, type=SegmentType.SPEECH),
            Segment(start=5.0, end=10.0, type=SegmentType.MUSIC),  # pyannote
            Segment(start=10.0, end=20.0, type=SegmentType.SPEECH),
        ]
        llm_cuts = [
            {"start": 15.0, "end": 18.0, "reason": "song intro", "confidence": 0.9},
        ]
        output_dir = tmp_path / "job"

        cutlist = reconcile(
            segments, llm_cuts, output_dir,
            total_duration=20.0, cut_pad_ms=0, min_keep_duration_s=0.0,
        )

        remove_intervals = [(d.start, d.end) for d in cutlist.remove_segments]
        # Both music region and LLM cut should be removed
        assert any(s <= 5.0 and e >= 10.0 for s, e in remove_intervals)
        assert any(s <= 15.0 and e >= 18.0 for s, e in remove_intervals)

    def test_min_keep_duration(self, tmp_path):
        """Short kept segments should be discarded."""
        segments = [
            Segment(start=0.0, end=1.0, type=SegmentType.SPEECH),  # too short
            Segment(start=1.0, end=8.0, type=SegmentType.MUSIC),
            Segment(start=8.0, end=10.0, type=SegmentType.SPEECH),
        ]
        output_dir = tmp_path / "job"

        cutlist = reconcile(
            segments, [], output_dir,
            total_duration=10.0, cut_pad_ms=0, min_keep_duration_s=1.5,
        )

        kept_durations = [d.duration for d in cutlist.keep_segments]
        assert all(d >= 1.5 for d in kept_durations)

    def test_output_file_created(self, tmp_path):
        segments = [Segment(start=0.0, end=10.0, type=SegmentType.SPEECH)]
        output_dir = tmp_path / "job"

        reconcile(segments, [], output_dir, total_duration=10.0)

        assert (output_dir / "cutlist_final.json").exists()
        data = json.loads((output_dir / "cutlist_final.json").read_text())
        assert "decisions" in data
        assert "total_duration" in data

    def test_all_speech(self, tmp_path):
        segments = [Segment(start=0.0, end=10.0, type=SegmentType.SPEECH)]
        output_dir = tmp_path / "job"

        cutlist = reconcile(segments, [], output_dir, total_duration=10.0)

        assert len(cutlist.keep_segments) >= 1
        assert cutlist.kept_duration == pytest.approx(10.0)

    def test_all_music(self, tmp_path):
        segments = [Segment(start=0.0, end=10.0, type=SegmentType.MUSIC)]
        output_dir = tmp_path / "job"

        cutlist = reconcile(
            segments, [], output_dir,
            total_duration=10.0, cut_pad_ms=0,
        )

        assert len(cutlist.keep_segments) == 0

    def test_padding_applied(self, tmp_path):
        segments = [
            Segment(start=0.0, end=5.0, type=SegmentType.SPEECH),
            Segment(start=5.0, end=10.0, type=SegmentType.MUSIC),
            Segment(start=10.0, end=20.0, type=SegmentType.SPEECH),
        ]
        output_dir = tmp_path / "job"

        cutlist = reconcile(
            segments, [], output_dir,
            total_duration=20.0, cut_pad_ms=300,
        )

        # The remove segment should be wider than 5-10 due to padding
        removes = cutlist.remove_segments
        assert len(removes) > 0
        rm = removes[0]
        assert rm.start < 5.0  # padded earlier
        assert rm.end > 10.0  # padded later

    def test_cutlist_roundtrip(self, tmp_path):
        segments = [
            Segment(start=0.0, end=5.0, type=SegmentType.SPEECH),
            Segment(start=5.0, end=10.0, type=SegmentType.MUSIC),
        ]
        output_dir = tmp_path / "job"

        original = reconcile(segments, [], output_dir, total_duration=10.0)
        loaded = CutList.load(output_dir / "cutlist_final.json")

        assert len(loaded.decisions) == len(original.decisions)
        assert loaded.total_duration == original.total_duration
