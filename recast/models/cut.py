"""CutList and Segment data models."""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path


class SegmentType(str, enum.Enum):
    SPEECH = "speech"
    MUSIC = "music"


class CutSource(str, enum.Enum):
    PYANNOTE = "pyannote"
    LLM = "llm"
    BOTH = "both"
    USER = "user"


@dataclass
class Segment:
    start: float
    end: float
    type: SegmentType = SegmentType.SPEECH

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "type": self.type.value}

    @classmethod
    def from_dict(cls, d: dict) -> Segment:
        return cls(
            start=d["start"],
            end=d["end"],
            type=SegmentType(d["type"]),
        )


@dataclass
class CutDecision:
    start: float
    end: float
    reason: str = ""
    confidence: float = 1.0
    source: CutSource = CutSource.PYANNOTE
    keep: bool = False  # True = keep this segment, False = remove it

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "reason": self.reason,
            "confidence": self.confidence,
            "source": self.source.value,
            "keep": self.keep,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CutDecision:
        return cls(
            start=d["start"],
            end=d["end"],
            reason=d.get("reason", ""),
            confidence=d.get("confidence", 1.0),
            source=CutSource(d.get("source", "pyannote")),
            keep=d.get("keep", False),
        )


@dataclass
class CutList:
    decisions: list[CutDecision] = field(default_factory=list)
    total_duration: float = 0.0

    @property
    def keep_segments(self) -> list[CutDecision]:
        return [d for d in self.decisions if d.keep]

    @property
    def remove_segments(self) -> list[CutDecision]:
        return [d for d in self.decisions if not d.keep]

    @property
    def kept_duration(self) -> float:
        return sum(d.duration for d in self.keep_segments)

    def to_dict(self) -> dict:
        return {
            "total_duration": self.total_duration,
            "decisions": [d.to_dict() for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> CutList:
        return cls(
            total_duration=d.get("total_duration", 0.0),
            decisions=[CutDecision.from_dict(x) for x in d.get("decisions", [])],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> CutList:
        data = json.loads(path.read_text())
        return cls.from_dict(data)
