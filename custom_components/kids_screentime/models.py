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
class QuietWindow:
    """Hours to disregard: on these weekdays (0 = Monday), between start and end (local "HH:MM"), for these apps.

    No apps means every app. An end at or before the start runs past midnight and belongs to the day it starts."""

    id: str
    apps: list[str]
    days: list[int]
    start: str
    end: str
    label: str = ""


@dataclass
class Rules:
    always: set[str] = field(default_factory=set)
    never: set[str] = field(default_factory=set)
    kids_apps: set[str] = field(default_factory=lambda: set(DEFAULT_KIDS_APPS))
    ignored_apps: set[str] = field(default_factory=lambda: {"youtube"})
    quiet_windows: list[QuietWindow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "always": sorted(self.always),
            "never": sorted(self.never),
            "kids_apps": sorted(self.kids_apps),
            "ignored_apps": sorted(self.ignored_apps),
            "quiet_windows": [asdict(w) for w in self.quiet_windows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rules:
        sets = {k: set(v) for k, v in data.items() if k in ("always", "never", "kids_apps", "ignored_apps")}
        windows = [QuietWindow(**w) for w in data.get("quiet_windows", [])]
        return cls(**sets, quiet_windows=windows)
