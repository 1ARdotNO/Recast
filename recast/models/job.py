"""Job data model."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


PIPELINE_STAGES = [
    "normalize",
    "segment",
    "transcribe",
    "llm_pass",
    "reconcile",
    "render",
    "metadata",
    "publish",
]


@dataclass
class Job:
    filename: str
    input_path: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    stage: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: str | None = None
    duration_s: float | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def fail(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.touch()

    def advance_stage(self, stage: str) -> None:
        if stage not in PIPELINE_STAGES:
            raise ValueError(f"Unknown stage: {stage}")
        self.stage = stage
        self.status = JobStatus.RUNNING
        self.touch()

    def complete(self) -> None:
        self.status = JobStatus.DONE
        self.touch()

    def set_review(self) -> None:
        self.status = JobStatus.REVIEW
        self.touch()
