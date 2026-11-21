"""Persistent storage for segments, shows, rules and the TMDB lookup cache."""
from __future__ import annotations

from typing import Any, Literal

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import Rules, Segment, Show, Verdict

STORAGE_VERSION = 1
SAVE_DELAY = 10


class ScreentimeStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, DOMAIN)
        self.segments: dict[str, Segment] = {}
        self.shows: dict[str, Show] = {}
        self.rules = Rules()
        self.lookups: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        self.segments = {k: Segment.from_dict(v) for k, v in data.get("segments", {}).items()}
        self.shows = {k: Show.from_dict(v) for k, v in data.get("shows", {}).items()}
        if "rules" in data:
            self.rules = Rules.from_dict(data["rules"])
        self.lookups = data.get("lookups", {})

    def _data(self) -> dict[str, Any]:
        return {
            "segments": {k: v.to_dict() for k, v in self.segments.items()},
            "shows": {k: v.to_dict() for k, v in self.shows.items()},
            "rules": self.rules.to_dict(),
            "lookups": self.lookups,
        }

    async def async_save(self) -> None:
        await self._store.async_save(self._data())

    def schedule_save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def add_segment(self, segment: Segment) -> None:
        self.segments[segment.id] = segment
        self.schedule_save()

    def delete_segment(self, segment_id: str) -> bool:
        if self.segments.pop(segment_id, None) is None:
            return False
        self.schedule_save()
        return True

    def _drop_segments(self, key: str) -> int:
        doomed = [sid for sid, seg in self.segments.items() if seg.show_key == key]
        for sid in doomed:
            del self.segments[sid]
        return len(doomed)

    def delete_show(self, key: str) -> int:
        removed = self._drop_segments(key)
        self.rules.never.add(key)
        self.rules.always.discard(key)
        self.schedule_save()
        return removed

    def set_rule(self, key: str, rule: Literal["always", "never"] | None) -> None:
        self.rules.always.discard(key)
        self.rules.never.discard(key)
        if rule == "always":
            self.rules.always.add(key)
        elif rule == "never":
            self.rules.never.add(key)
        self.schedule_save()

    def resolve_review(self, key: str, count: bool) -> None:
        show = self.shows.get(key)
        if count:
            self.set_rule(key, "always")
            if show:
                show.verdict = Verdict.COUNT
                show.source = "manual"
        else:
            self._drop_segments(key)
            self.set_rule(key, "never")
            if show:
                show.verdict = Verdict.DISCARD
                show.source = "manual"
        self.schedule_save()

    def upsert_show(self, show: Show) -> None:
        self.shows[show.key] = show
        self.schedule_save()
