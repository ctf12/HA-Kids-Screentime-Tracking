"""Turn Apple TV media_player state changes into play segments."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import FLUSH_INTERVAL, MIN_SEGMENT_SECONDS, SIGNAL_UPDATED
from .models import Segment, Verdict, show_key
from .resolver import ShowResolver
from .store import ScreentimeStore

# Attribute names, from HA's apple_tv media_player. Verified against the real TVs in the spike.
ATTR_CONTENT_TYPE = "media_content_type"
ATTR_TITLE = "media_title"
ATTR_SERIES = "media_series_title"
ATTR_SEASON = "media_season"
ATTR_EPISODE = "media_episode"
ATTR_POSITION = "media_position"
ATTR_POSITION_AT = "media_position_updated_at"
ATTR_DURATION = "media_duration"
ATTR_APP_ID = "app_id"
ATTR_APP_NAME = "app_name"

VIDEO_TYPES = {"tvshow", "movie", "video"}


@dataclass
class _Open:
    device: str
    item: tuple
    start: datetime
    app_id: str | None
    app_name: str | None
    title: str | None
    series: str | None
    season: int | None
    episode: int | None
    media_type: str
    position_max: float | None = None
    duration_total: float | None = None


def _estimate_position(attrs: dict[str, Any], now: datetime) -> float | None:
    position = attrs.get(ATTR_POSITION)
    if position is None:
        return None
    updated = attrs.get(ATTR_POSITION_AT)
    if isinstance(updated, datetime):
        return float(position) + max(0.0, (now - updated).total_seconds())
    return float(position)


class SessionTracker:
    def __init__(
        self, hass: HomeAssistant, store: ScreentimeStore, resolver: ShowResolver, players: list[str]
    ) -> None:
        self._hass = hass
        self._store = store
        self._resolver = resolver
        self._players = players
        self._open: dict[str, _Open] = {}

    @staticmethod
    def _item(state: State | None) -> _Open | None:
        if state is None or state.state != "playing":
            return None
        a = state.attributes
        content_type = a.get(ATTR_CONTENT_TYPE)
        if content_type is not None and str(content_type).lower() not in VIDEO_TYPES:
            return None
        app_id, title = a.get(ATTR_APP_ID), a.get(ATTR_TITLE)
        if content_type is None and not (app_id or title):
            return None
        series = a.get(ATTR_SERIES)
        return _Open(
            device=state.entity_id,
            item=(app_id, title, series, a.get(ATTR_SEASON), a.get(ATTR_EPISODE)),
            start=dt_util.utcnow(), app_id=app_id, app_name=a.get(ATTR_APP_NAME), title=title,
            series=series, season=a.get(ATTR_SEASON), episode=a.get(ATTR_EPISODE),
            media_type=str(content_type or "video").lower(), duration_total=a.get(ATTR_DURATION),
        )

    async def async_handle_state(self, entity_id: str, new: State | None, now: datetime) -> None:
        candidate = self._item(new)
        current = self._open.get(entity_id)
        closing: _Open | None = None
        if current is not None and (candidate is None or candidate.item != current.item):
            closing = self._open.pop(entity_id)
            current = None
        if candidate is not None:
            if current is None:
                candidate.start = now
                self._open[entity_id] = current = candidate
            assert new is not None
            position = _estimate_position(new.attributes, now)
            if position is not None:
                current.position_max = max(current.position_max or 0.0, position)
            if new.attributes.get(ATTR_DURATION) is not None:
                current.duration_total = new.attributes[ATTR_DURATION]
        if closing is not None:
            await self._emit(closing, now)

    async def _emit(self, seg: _Open, end: datetime) -> None:
        seconds = int((end - seg.start).total_seconds())
        if seconds < MIN_SEGMENT_SECONDS:
            return
        name = seg.series or seg.title
        key = show_key(name) if name else show_key(f"app:{seg.app_id or 'unknown'}")
        title = name or seg.app_name or "Unknown title"
        show = await self._resolver.resolve(
            key=key, title=title, media_type=seg.media_type, app_name=seg.app_name, now=end
        )
        if show.verdict == Verdict.DISCARD:
            return
        self._store.add_segment(Segment(
            id=uuid.uuid4().hex, device=seg.device, app_id=seg.app_id, app_name=seg.app_name,
            title=seg.title or title, series=seg.series, season=seg.season, episode=seg.episode,
            media_type=seg.media_type, show_key=key, start=seg.start, end=end, seconds=seconds,
            position_max=seg.position_max, duration_total=seg.duration_total,
        ))
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)

    async def async_flush(self, now: datetime) -> None:
        """Close every open segment and reopen it, so a crash loses at most one interval."""
        for entity_id, seg in list(self._open.items()):
            done = replace(seg)
            seg.start = now
            await self._emit(done, now)

    async def async_close_all(self, now: datetime) -> None:
        opened, self._open = list(self._open.values()), {}
        for seg in opened:
            await self._emit(seg, now)
        await self._store.async_save()

    def async_start(self) -> Callable[[], None]:
        @callback
        def _changed(event: Event) -> None:
            entity_id = event.data["entity_id"]
            self._hass.async_create_task(
                self.async_handle_state(entity_id, event.data.get("new_state"), dt_util.utcnow())
            )

        @callback
        def _tick(_now: datetime) -> None:
            self._hass.async_create_task(self.async_flush(dt_util.utcnow()))

        async def _stop(_event: Event) -> None:
            await self.async_close_all(dt_util.utcnow())

        for entity_id in self._players:
            state = self._hass.states.get(entity_id)
            if state is not None:
                self._hass.async_create_task(
                    self.async_handle_state(entity_id, state, dt_util.utcnow())
                )
        unsubs = [
            async_track_state_change_event(self._hass, self._players, _changed),
            async_track_time_interval(self._hass, _tick, FLUSH_INTERVAL),
            self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop),
        ]

        def _unsub() -> None:
            for unsub in unsubs:
                unsub()

        return _unsub
