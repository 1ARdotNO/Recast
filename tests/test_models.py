"""Tests for data models."""

import json
from pathlib import Path

import pytest

from recast.models.job import Job, JobStatus, PIPELINE_STAGES
from recast.models.show import ShowConfig
from recast.models.cut import (
    CutList, CutDecision, Segment, SegmentType, CutSource,
)
from recast.models.episode import Episode, Chapter


# --- Job tests ---

class TestJob:
    def test_defaults(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        assert job.status == JobStatus.QUEUED
        assert job.stage is None
        assert job.error is None
        assert job.id  # UUID generated

    def test_fail(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        job.fail("something broke")
        assert job.status == JobStatus.FAILED
        assert job.error == "something broke"

    def test_advance_stage(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        job.advance_stage("normalize")
        assert job.stage == "normalize"
        assert job.status == JobStatus.RUNNING

    def test_advance_stage_invalid(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        with pytest.raises(ValueError, match="Unknown stage"):
            job.advance_stage("invalid_stage")

    def test_complete(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        job.complete()
        assert job.status == JobStatus.DONE

    def test_set_review(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        job.set_review()
        assert job.status == JobStatus.REVIEW

    def test_touch_updates_timestamp(self):
        job = Job(filename="test.mp3", input_path="/input/test.mp3")
        old_ts = job.updated_at
        job.touch()
        assert job.updated_at >= old_ts

    def test_pipeline_stages_list(self):
        assert len(PIPELINE_STAGES) == 8
        assert PIPELINE_STAGES[0] == "normalize"
        assert PIPELINE_STAGES[-1] == "publish"


# --- ShowConfig tests ---

class TestShowConfig:
    def test_defaults(self):
        cfg = ShowConfig()
        assert cfg.name == "Untitled Show"
        assert cfg.language == "no"
        assert cfg.whisper_model == "NbAiLab/nb-whisper-small"
        assert cfg.ollama_model == "gemma3:12b"
        assert cfg.join_mode == "crossfade"
        assert cfg.crossfade_duration_ms == 300
        assert cfg.min_keep_duration_s == 2.0

    def test_paths(self, tmp_path):
        cfg = ShowConfig(show_folder=tmp_path)
        assert cfg.watch_path == tmp_path / "incoming"
        assert cfg.output_path == tmp_path / "episodes"
        assert cfg.recast_dir == tmp_path / ".recast"
        assert cfg.db_path == tmp_path / ".recast" / "recast.db"

    def test_job_dir(self, tmp_path):
        cfg = ShowConfig(show_folder=tmp_path)
        assert cfg.job_dir("abc") == tmp_path / ".recast" / "jobs" / "abc"

    def test_file_patterns_default(self):
        cfg = ShowConfig()
        assert "*.mp3" in cfg.file_patterns
        assert "*.wav" in cfg.file_patterns


# --- Segment tests ---

class TestSegment:
    def test_duration(self):
        seg = Segment(start=1.0, end=3.5, type=SegmentType.SPEECH)
        assert seg.duration == pytest.approx(2.5)

    def test_roundtrip(self):
        seg = Segment(start=1.0, end=3.5, type=SegmentType.MUSIC)
        d = seg.to_dict()
        assert d == {"start": 1.0, "end": 3.5, "type": "music"}
        restored = Segment.from_dict(d)
        assert restored.start == seg.start
        assert restored.end == seg.end
        assert restored.type == seg.type


# --- CutDecision tests ---

class TestCutDecision:
    def test_defaults(self):
        cd = CutDecision(start=0.0, end=5.0)
        assert cd.keep is False
        assert cd.source == CutSource.PYANNOTE
        assert cd.duration == pytest.approx(5.0)

    def test_roundtrip(self):
        cd = CutDecision(
            start=1.0, end=4.0, reason="song intro",
            confidence=0.85, source=CutSource.LLM, keep=False,
        )
        d = cd.to_dict()
        restored = CutDecision.from_dict(d)
        assert restored.start == cd.start
        assert restored.end == cd.end
        assert restored.reason == cd.reason
        assert restored.confidence == cd.confidence
        assert restored.source == cd.source
        assert restored.keep == cd.keep


# --- CutList tests ---

class TestCutList:
    def test_keep_remove_segments(self):
        cl = CutList(decisions=[
            CutDecision(start=0, end=5, keep=True),
            CutDecision(start=5, end=10, keep=False),
            CutDecision(start=10, end=15, keep=True),
        ], total_duration=15.0)
        assert len(cl.keep_segments) == 2
        assert len(cl.remove_segments) == 1
        assert cl.kept_duration == pytest.approx(10.0)

    def test_roundtrip(self):
        cl = CutList(
            decisions=[
                CutDecision(start=0, end=5, keep=True, reason="speech"),
                CutDecision(start=5, end=10, keep=False, reason="music"),
            ],
            total_duration=10.0,
        )
        d = cl.to_dict()
        restored = CutList.from_dict(d)
        assert len(restored.decisions) == 2
        assert restored.total_duration == 10.0
        assert restored.decisions[0].keep is True

    def test_save_load(self, tmp_path):
        cl = CutList(
            decisions=[CutDecision(start=0, end=5, keep=True)],
            total_duration=5.0,
        )
        path = tmp_path / "cutlist.json"
        cl.save(path)
        loaded = CutList.load(path)
        assert len(loaded.decisions) == 1
        assert loaded.total_duration == 5.0

    def test_empty(self):
        cl = CutList()
        assert cl.keep_segments == []
        assert cl.remove_segments == []
        assert cl.kept_duration == 0.0


# --- Chapter tests ---

class TestChapter:
    def test_roundtrip(self):
        ch = Chapter(title="Introduction", start_time=0.0)
        d = ch.to_dict()
        assert d == {"title": "Introduction", "start_time": 0.0}
        restored = Chapter.from_dict(d)
        assert restored.title == ch.title
        assert restored.start_time == ch.start_time


# --- Episode tests ---

class TestEpisode:
    def test_defaults(self):
        ep = Episode(job_id="abc")
        assert ep.title == ""
        assert ep.chapters == []
        assert ep.feed_updated is False

    def test_roundtrip(self):
        ep = Episode(
            job_id="abc",
            title="Test Episode",
            description="A test",
            duration_s=120.0,
            chapters=[Chapter(title="Part 1", start_time=0.0)],
        )
        d = ep.to_dict()
        restored = Episode.from_dict(d)
        assert restored.job_id == ep.job_id
        assert restored.title == ep.title
        assert len(restored.chapters) == 1
        assert restored.chapters[0].title == "Part 1"

    def test_save_load(self, tmp_path):
        ep = Episode(
            job_id="abc",
            title="Saved Episode",
            chapters=[Chapter(title="Ch1", start_time=0.0)],
        )
        path = tmp_path / "episode.json"
        ep.save(path)
        loaded = Episode.load(path)
        assert loaded.title == "Saved Episode"
        assert len(loaded.chapters) == 1
