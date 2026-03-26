"""Episode output model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Chapter:
    title: str
    start_time: float  # seconds

    def to_dict(self) -> dict:
        return {"title": self.title, "start_time": self.start_time}

    @classmethod
    def from_dict(cls, d: dict) -> Chapter:
        return cls(title=d["title"], start_time=d["start_time"])


@dataclass
class Episode:
    job_id: str
    output_path: str = ""
    title: str = ""
    description: str = ""
    duration_s: float = 0.0
    published_at: str | None = None
    feed_updated: bool = False
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "output_path": self.output_path,
            "title": self.title,
            "description": self.description,
            "duration_s": self.duration_s,
            "published_at": self.published_at,
            "feed_updated": self.feed_updated,
            "chapters": [c.to_dict() for c in self.chapters],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Episode:
        return cls(
            job_id=d["job_id"],
            output_path=d.get("output_path", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            duration_s=d.get("duration_s", 0.0),
            published_at=d.get("published_at"),
            feed_updated=d.get("feed_updated", False),
            chapters=[Chapter.from_dict(c) for c in d.get("chapters", [])],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> Episode:
        data = json.loads(path.read_text())
        return cls.from_dict(data)
