"""Tests for SQLite job queue."""

import pytest

from recast.models.job import JobStatus
from recast.models.episode import Episode, Chapter
from recast.queue import JobQueue


@pytest.fixture
def queue(tmp_path):
    return JobQueue(tmp_path / ".recast" / "recast.db")


class TestJobQueue:
    def test_create_and_get(self, queue):
        job = queue.create_job("test.mp3", "/input/test.mp3")
        assert job.status == JobStatus.QUEUED
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.filename == "test.mp3"
        assert fetched.input_path == "/input/test.mp3"

    def test_get_nonexistent(self, queue):
        assert queue.get_job("nonexistent") is None

    def test_update_job(self, queue):
        job = queue.create_job("test.mp3", "/input/test.mp3")
        job.advance_stage("normalize")
        queue.update_job(job)
        fetched = queue.get_job(job.id)
        assert fetched.status == JobStatus.RUNNING
        assert fetched.stage == "normalize"

    def test_fail_job(self, queue):
        job = queue.create_job("test.mp3", "/input/test.mp3")
        job.fail("ffmpeg error")
        queue.update_job(job)
        fetched = queue.get_job(job.id)
        assert fetched.status == JobStatus.FAILED
        assert fetched.error == "ffmpeg error"

    def test_list_jobs(self, queue):
        queue.create_job("a.mp3", "/a.mp3")
        queue.create_job("b.mp3", "/b.mp3")
        jobs = queue.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_filter_status(self, queue):
        job = queue.create_job("a.mp3", "/a.mp3")
        queue.create_job("b.mp3", "/b.mp3")
        job.complete()
        queue.update_job(job)
        done_jobs = queue.list_jobs(status=JobStatus.DONE)
        assert len(done_jobs) == 1
        assert done_jobs[0].id == job.id

    def test_list_jobs_pagination(self, queue):
        for i in range(5):
            queue.create_job(f"{i}.mp3", f"/{i}.mp3")
        page = queue.list_jobs(limit=2, offset=0)
        assert len(page) == 2
        page2 = queue.list_jobs(limit=2, offset=2)
        assert len(page2) == 2

    def test_tables_created(self, queue):
        assert "jobs" in queue.db.table_names()
        assert "episodes" in queue.db.table_names()


class TestEpisodeQueue:
    def test_create_and_get(self, queue):
        job = queue.create_job("test.mp3", "/input/test.mp3")
        ep = Episode(
            job_id=job.id,
            output_path="/output/ep.mp3",
            title="Test Episode",
            description="A test.",
            duration_s=120.0,
            chapters=[Chapter(title="Intro", start_time=0.0)],
        )
        queue.create_episode(ep)
        fetched = queue.get_episode(job.id)
        assert fetched is not None
        assert fetched.title == "Test Episode"
        assert fetched.duration_s == 120.0
        assert len(fetched.chapters) == 1
        assert fetched.chapters[0].title == "Intro"

    def test_get_nonexistent(self, queue):
        assert queue.get_episode("nonexistent") is None

    def test_update_episode(self, queue):
        job = queue.create_job("test.mp3", "/input/test.mp3")
        ep = Episode(job_id=job.id, title="Original")
        queue.create_episode(ep)
        ep.title = "Updated"
        ep.feed_updated = True
        queue.update_episode(ep)
        fetched = queue.get_episode(job.id)
        assert fetched.title == "Updated"
        assert fetched.feed_updated is True
