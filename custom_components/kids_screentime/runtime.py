"""Objects shared by the integration's platforms and APIs for one config entry."""
from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .resolver import ShowResolver
from .store import ScreentimeStore
from .tracker import SessionTracker


@dataclass
class RuntimeData:
    store: ScreentimeStore
    resolver: ShowResolver
    tracker: SessionTracker
    tz: ZoneInfo
    week_start: int
