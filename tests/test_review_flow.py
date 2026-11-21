from datetime import datetime, timedelta, timezone

import pytest
from homeassistant.core import State

from custom_components.kids_screentime.models import Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.tmdb import Lookup, TmdbError
from custom_components.kids_screentime.tracker import SessionTracker

TV = "media_player.great_room_apple_tv"
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
ATTRS = dict(
    media_content_type="tvshow", media_title="Ep", media_series_title="Bluey", media_season=1,
    media_episode=1, app_id="com.disney.disneyplus", app_name="Disney+", media_duration=420,
)


class FlakyTmdb:
    def __init__(self, fail_first=True):
        self.fail = fail_first

    async def lookup(self, title, media_type, year=None):
        if self.fail:
            self.fail = False
            raise TmdbError("outage")
        return Lookup(1, "TV-Y", True)


@pytest.fixture
async def parts(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    return SessionTracker(hass, store, ShowResolver(store, FlakyTmdb()), [TV]), store


async def watch(tracker, start_s, length=300):
    at = lambda s: T0 + timedelta(seconds=s)
    await tracker.async_handle_state(TV, State(TV, "playing", ATTRS), at(start_s))
    await tracker.async_handle_state(TV, State(TV, "paused", ATTRS), at(start_s + length))


async def test_tmdb_outage_titles_go_to_review_then_resolve_on_retry(parts):
    tracker, store = parts
    await watch(tracker, 0)
    assert store.shows["bluey"].verdict == Verdict.REVIEW and store.shows["bluey"].lookup_failed
    assert len(store.segments) == 1
    await watch(tracker, 1000)
    assert store.shows["bluey"].verdict == Verdict.COUNT
    assert len(store.segments) == 2


async def test_approving_review_keeps_segments_and_sets_always(parts):
    tracker, store = parts
    await watch(tracker, 0)
    store.resolve_review("bluey", True)
    assert len(store.segments) == 1
    assert "bluey" in store.rules.always


async def test_rejecting_review_removes_segments_and_blocks_title(parts):
    tracker, store = parts
    await watch(tracker, 0)
    store.resolve_review("bluey", False)
    assert not store.segments
    await watch(tracker, 1000)
    assert not store.segments
