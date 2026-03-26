"""SQLite job queue."""

from __future__ import annotations

import json
from pathlib import Path

import sqlite_utils

from recast.models.job import Job, JobStatus
from recast.models.episode import Episode, Chapter


class JobQueue:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite_utils.Database(str(db_path))
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        if "jobs" not in self.db.table_names():
            self.db["jobs"].create({
                "id": str,
                "filename": str,
                "input_path": str,
                "status": str,
                "stage": str,
                "created_at": str,
                "updated_at": str,
                "error": str,
                "duration_s": float,
            }, pk="id")

        if "episodes" not in self.db.table_names():
            self.db["episodes"].create({
                "job_id": str,
                "output_path": str,
                "title": str,
                "description": str,
                "duration_s": float,
                "published_at": str,
                "feed_updated": int,
                "chapters_json": str,
            }, pk="job_id", foreign_keys=[("job_id", "jobs", "id")])

    def create_job(self, filename: str, input_path: str) -> Job:
        job = Job(filename=filename, input_path=input_path)
        self.db["jobs"].insert({
            "id": job.id,
            "filename": job.filename,
            "input_path": job.input_path,
            "status": job.status.value,
            "stage": job.stage,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "error": job.error,
            "duration_s": job.duration_s,
        })
        return job

    def get_job(self, job_id: str) -> Job | None:
        try:
            row = self.db["jobs"].get(job_id)
        except sqlite_utils.db.NotFoundError:
            return None
        return self._row_to_job(row)

    def update_job(self, job: Job) -> None:
        job.touch()
        self.db["jobs"].update(job.id, {
            "status": job.status.value,
            "stage": job.stage,
            "updated_at": job.updated_at,
            "error": job.error,
            "duration_s": job.duration_s,
        })

    def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: list = []
        if status is not None:
            sql += " WHERE status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.db.execute(sql, params).fetchall()
        cols = [d[0] for d in self.db.execute(sql, params).description]
        # Re-fetch with column names
        rows = [
            dict(zip(cols, row))
            for row in self.db.execute(sql, params).fetchall()
        ]
        return [self._row_to_job(r) for r in rows]

    def create_episode(self, episode: Episode) -> None:
        self.db["episodes"].insert({
            "job_id": episode.job_id,
            "output_path": episode.output_path,
            "title": episode.title,
            "description": episode.description,
            "duration_s": episode.duration_s,
            "published_at": episode.published_at,
            "feed_updated": 1 if episode.feed_updated else 0,
            "chapters_json": json.dumps([c.to_dict() for c in episode.chapters]),
        })

    def get_episode(self, job_id: str) -> Episode | None:
        try:
            row = self.db["episodes"].get(job_id)
        except sqlite_utils.db.NotFoundError:
            return None
        return self._row_to_episode(row)

    def update_episode(self, episode: Episode) -> None:
        self.db["episodes"].update(episode.job_id, {
            "output_path": episode.output_path,
            "title": episode.title,
            "description": episode.description,
            "duration_s": episode.duration_s,
            "published_at": episode.published_at,
            "feed_updated": 1 if episode.feed_updated else 0,
            "chapters_json": json.dumps([c.to_dict() for c in episode.chapters]),
        })

    @staticmethod
    def _row_to_job(row: dict) -> Job:
        return Job(
            id=row["id"],
            filename=row["filename"],
            input_path=row["input_path"],
            status=JobStatus(row["status"]),
            stage=row.get("stage"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row.get("error"),
            duration_s=row.get("duration_s"),
        )

    @staticmethod
    def _row_to_episode(row: dict) -> Episode:
        chapters_raw = json.loads(row.get("chapters_json") or "[]")
        return Episode(
            job_id=row["job_id"],
            output_path=row.get("output_path", ""),
            title=row.get("title", ""),
            description=row.get("description", ""),
            duration_s=row.get("duration_s", 0.0),
            published_at=row.get("published_at"),
            feed_updated=bool(row.get("feed_updated", 0)),
            chapters=[Chapter.from_dict(c) for c in chapters_raw],
        )
