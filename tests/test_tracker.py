from datetime import datetime, timedelta, timezone

import pytest
from homeassistant.core import State

from custom_components.kids_screentime.models import Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.tmdb import Lookup
from custom_components.kids_screentime.tracker import SessionTracker

TV = "media_player.great_room_apple_tv"
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


class FakeTmdb:
    async def lookup(self, title, media_type, year=None):
        return Lookup(1, "TV-Y", True) if title.casefold() == "bluey" else None


def state(value, **attrs):
    return State(TV, value, attrs)


def bluey(episode=1, **extra):
    return dict(
        media_content_type="tvshow", media_title=f"Episode {episode}", media_series_title="Bluey",
        media_season=1, media_episode=episode, app_id="com.disney.disneyplus", app_name="Disney+",
        media_duration=420, media_position=0, **extra,
    )


@pytest.fixture
async def parts(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    resolver = ShowResolver(store, FakeTmdb())
    return SessionTracker(hass, store, resolver, [TV]), store


def seconds(store):
    return sorted(s.seconds for s in store.segments.values())


async def test_playing_then_paused_makes_one_segment(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(600))
    assert seconds(store) == [600]
    seg = next(iter(store.segments.values()))
    assert seg.show_key == "bluey" and seg.device == TV and seg.app_name == "Disney+"
    assert store.shows["bluey"].verdict == Verdict.COUNT


async def test_pause_resume_same_episode_two_segments_same_show_key(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(100))
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(200))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(500))
    assert seconds(store) == [100, 300]
    assert {s.show_key for s in store.segments.values()} == {"bluey"}


async def test_title_change_starts_new_segment(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey(1)), at(0))
    await tracker.async_handle_state(TV, state("playing", **bluey(2)), at(300))
    await tracker.async_handle_state(TV, state("paused", **bluey(2)), at(600))
    assert seconds(store) == [300, 300]
    assert sorted(s.episode for s in store.segments.values()) == [1, 2]


async def test_segment_under_15s_dropped(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(14))
    assert not store.segments


async def test_music_content_type_ignored(parts):
    tracker, store = parts
    music = dict(media_content_type="music", media_title="Song", app_id="com.apple.TVMusic", app_name="Music")
    await tracker.async_handle_state(TV, state("playing", **music), at(0))
    await tracker.async_handle_state(TV, state("paused", **music), at(300))
    assert not store.segments and not store.shows


async def test_youtube_ignored(parts):
    tracker, store = parts
    yt = dict(bluey(), app_id="com.google.ios.youtube", app_name="YouTube")
    await tracker.async_handle_state(TV, state("playing", **yt), at(0))
    await tracker.async_handle_state(TV, state("paused", **yt), at(300))
    assert not store.segments


async def test_unavailable_state_closes_segment(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("unavailable"), at(100))
    assert seconds(store) == [100]


async def test_flush_splits_without_losing_or_doubling_time(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_flush(at(300))
    await tracker.async_flush(at(600))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(720))
    assert seconds(store) == [120, 300, 300]
    assert sum(seconds(store)) == 720


async def test_no_title_kids_app_counts_under_app_key(parts):
    tracker, store = parts
    junior = dict(media_content_type="video", app_id="com.disney.junior", app_name="Disney Junior")
    await tracker.async_handle_state(TV, state("playing", **junior), at(0))
    await tracker.async_handle_state(TV, state("paused", **junior), at(300))
    seg = next(iter(store.segments.values()))
    assert seg.show_key == "app:com.disney.junior"
    assert store.shows[seg.show_key].verdict == Verdict.COUNT


async def test_no_title_other_app_goes_to_review(parts):
    tracker, store = parts
    other = dict(media_content_type="video", app_id="com.netflix.Netflix", app_name="Netflix")
    await tracker.async_handle_state(TV, state("playing", **other), at(0))
    await tracker.async_handle_state(TV, state("paused", **other), at(300))
    assert store.shows["app:com.netflix.netflix"].verdict == Verdict.REVIEW
    assert seconds(store) == [300]


async def test_open_segment_discarded_if_show_deleted_before_close(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    store.delete_show("bluey")
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(300))
    assert not store.segments


async def test_deleted_show_stays_blocked_on_next_play(parts):
    tracker, store = parts
    store.delete_show("bluey")
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(300))
    assert not store.segments
