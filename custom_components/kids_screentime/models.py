"""Data models for Kids Screentime Tracking."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from .const import DEFAULT_KIDS_APPS


class Verdict(StrEnum):
    COUNT = "count"
    DISCARD = "discard"
    REVIEW = "review"


_YEAR_SUFFIX = re.compile(r"\s*\(\d{4}\)\s*$")


def show_key(name: str) -> str:
    """Normalise a title so 'Bluey (2018)' and ' bluey ' are the same show."""
    name = _YEAR_SUFFIX.sub("", name.casefold().strip())
    return re.sub(r"\s+", " ", name)


@dataclass
class Segment:
    id: str
    device: str
    app_id: str | None
    app_name: str | None
    title: str
    series: str | None
    season: int | None
    episode: int | None
    media_type: str
    show_key: str
    start: datetime
    end: datetime
    seconds: int
    position_max: float | None
    duration_total: float | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Segment:
        data = dict(data)
        data["start"] = datetime.fromisoformat(data["start"])
        data["end"] = datetime.fromisoformat(data["end"])
        return cls(**data)


@dataclass
class Show:
    key: str
    title: str
    rating: str | None
    tmdb_id: int | None
    kids_genre: bool
    verdict: Verdict
    source: Literal["auto", "manual"]
    lookup_failed: bool
    first_seen: datetime
    last_seen: datetime
    exact: bool = True  # False when TMDB only loosely matched the title

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        data["first_seen"] = self.first_seen.isoformat()
        data["last_seen"] = self.last_seen.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Show:
        data = dict(data)
        data["verdict"] = Verdict(data["verdict"])
        data["first_seen"] = datetime.fromisoformat(data["first_seen"])
        data["last_seen"] = datetime.fromisoformat(data["last_seen"])
        return cls(**data)


@dataclass
class Rules:
    always: set[str] = field(default_factory=set)
    never: set[str] = field(default_factory=set)
    kids_apps: set[str] = field(default_factory=lambda: set(DEFAULT_KIDS_APPS))
    ignored_apps: set[str] = field(default_factory=lambda: {"youtube"})

    def to_dict(self) -> dict[str, list[str]]:
        return {f.name: sorted(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, list[str]]) -> Rules:
        return cls(**{k: set(v) for k, v in data.items()})
