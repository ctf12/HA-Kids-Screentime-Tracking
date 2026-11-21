"""Turn Apple TV media_player state changes into play segments."""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .classifier import app_matches
from .const import FLUSH_INTERVAL, MIN_SEGMENT_SECONDS, SIGNAL_UPDATED, STITCH_GAP_SECONDS
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

ATTR_ARTIST = "media_artist"
VIDEO_TYPES = {"tvshow", "movie", "video"}

# Apps rarely fill the series fields. What the live house actually sends (see docs/apple-tv-attributes.md):
#   Disney+: media_title = the series, media_artist = "S1:E21 Milk"
#   Crave:   media_title = "Friends \u2011 S1 E5 The One With ..." (a non-breaking hyphen)
#   Netflix: nothing but the app
_EPISODE_ARTIST = re.compile(r"^S(\d+)\s*[:.]?\s*E(\d+)\b", re.IGNORECASE)
_EPISODE_TITLE = re.compile(r"^(?P<series>.+?)\s*[-\u2010-\u2015]\s*S(?P<s>\d+)\s*[:.]?\s*E(?P<e>\d+)\b", re.IGNORECASE)


def episode_info(attrs: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """Series, season and episode: from the proper attributes when sent, else read out of the artist or the title."""
    series, season, episode = attrs.get(ATTR_SERIES), attrs.get(ATTR_SEASON), attrs.get(ATTR_EPISODE)
    if series is not None or season is not None or episode is not None:
        return series, season, episode
    title, artist = attrs.get(ATTR_TITLE), attrs.get(ATTR_ARTIST)
    if isinstance(title, str) and isinstance(artist, str):
        m = _EPISODE_ARTIST.match(artist.strip())
        if m:
            return title.strip(), int(m.group(1)), int(m.group(2))
    if isinstance(title, str):
        m = _EPISODE_TITLE.match(title.strip())
        if m:
            return m.group("series").strip(), int(m.group("s")), int(m.group("e"))
    return None, None, None


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
    segment_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    position_max: float | None = None
    duration_total: float | None = None


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _show_key_of(seg: "_Open") -> str:
    name = seg.series or seg.title
    return show_key(name) if name else show_key(f"app:{seg.app_id or seg.app_name or 'unknown'}")


@dataclass
class _Recent:
    """The viewing that just ended on one TV, so a resume within the gap can carry on the same row."""

    segment_id: str
    start: datetime
    end: datetime
    app_id: str | None
    key: str


def _estimate_position(attrs: dict[str, Any], now: datetime) -> float | None:
    position = _number(attrs.get(ATTR_POSITION))
    if position is None:
        return None
    updated = attrs.get(ATTR_POSITION_AT)
    if isinstance(updated, datetime):
        return position + max(0.0, (now - updated).total_seconds())
    return position


class SessionTracker:
    def __init__(
        self, hass: HomeAssistant, store: ScreentimeStore, resolver: ShowResolver, players: list[str]
    ) -> None:
        self._hass = hass
        self._store = store
        self._resolver = resolver
        self._players = players
        self._open: dict[str, _Open] = {}
        self._recent: dict[str, _Recent] = {}
        self._pending: set[str] = set()  # rows closed whose save is still awaiting a lookup

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
        series, season, episode = episode_info(a)
        return _Open(
            device=state.entity_id,
            item=(app_id, title, series, season, episode),
            start=dt_util.utcnow(), app_id=app_id, app_name=a.get(ATTR_APP_NAME), title=title,
            series=series, season=season, episode=episode,
            media_type=str(content_type or "video").lower(), duration_total=_number(a.get(ATTR_DURATION)),
        )

    async def async_handle_state(self, entity_id: str, new: State | None, now: datetime) -> None:
        candidate = self._item(new)
        current = self._open.get(entity_id)
        closing: _Open | None = None
        if current is not None and (candidate is None or candidate.item != current.item):
            closing = self._open.pop(entity_id)
            self._recent[entity_id] = _Recent(closing.segment_id, closing.start, now, closing.app_id, _show_key_of(closing))
            self._pending.add(closing.segment_id)
            current = None
        if candidate is not None:
            if current is None:
                candidate.start = now
                self._stitch(entity_id, candidate, now)
                self._open[entity_id] = current = candidate
            assert new is not None
            position = _estimate_position(new.attributes, now)
            if position is not None:
                current.position_max = max(current.position_max or 0.0, position)
            duration = _number(new.attributes.get(ATTR_DURATION))
            if duration is not None:
                current.duration_total = duration
        if closing is not None:
            await self._emit(closing, now)

    def _stitch(self, entity_id: str, candidate: _Open, now: datetime) -> None:
        """Carry on the previous row when the same app and show resumes within the gap (same id, original start)."""
        recent = self._recent.get(entity_id)
        if recent is None or (now - recent.end).total_seconds() > STITCH_GAP_SECONDS:
            return
        still_there = recent.segment_id in self._store.segments or recent.segment_id in self._pending
        if still_there and recent.app_id == candidate.app_id and recent.key == _show_key_of(candidate):
            candidate.segment_id = recent.segment_id
            candidate.start = recent.start
            del self._recent[entity_id]

    async def _emit(self, seg: _Open, end: datetime) -> None:
        try:
            await self._emit_row(seg, end)
        finally:
            self._pending.discard(seg.segment_id)

    async def _emit_row(self, seg: _Open, end: datetime) -> None:
        seconds = int((end - seg.start).total_seconds())
        if seconds < MIN_SEGMENT_SECONDS:
            return
        if app_matches(seg.app_name, self._store.rules.ignored_apps):
            return  # ignored apps (YouTube) are dropped before any lookup or show is created
        name = seg.series or seg.title
        key = _show_key_of(seg)
        title = name or seg.app_name or "Unknown title"
        show = await self._resolver.resolve(
            key=key, title=title, media_type=seg.media_type, app_name=seg.app_name, now=end
        )
        if show.verdict == Verdict.DISCARD:
            return
        self._store.add_segment(Segment(
            id=seg.segment_id, device=seg.device, app_id=seg.app_id, app_name=seg.app_name,
            title=seg.title or title, series=seg.series, season=seg.season, episode=seg.episode,
            media_type=seg.media_type, show_key=key, start=seg.start, end=end, seconds=seconds,
            position_max=seg.position_max, duration_total=seg.duration_total,
        ))
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)

    async def async_flush(self, now: datetime) -> None:
        """Save every open segment as it stands, so a crash loses at most one interval."""
        for entity_id, seg in list(self._open.items()):
            if self._open.get(entity_id) is not seg:
                continue  # it closed while an earlier lookup was awaited; never emit it twice
            await self._emit(seg, now)  # same row id each time: this updates the one in-progress record

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
