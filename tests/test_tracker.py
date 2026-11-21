from datetime import datetime, timedelta, timezone

import pytest
from homeassistant.core import State

from custom_components.kids_screentime.models import Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.summary import build_summary
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


async def test_flush_keeps_one_row_without_losing_or_doubling_time(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_flush(at(300))
    assert seconds(store) == [300]
    await tracker.async_flush(at(600))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(720))
    assert seconds(store) == [720]
    assert len(store.segments) == 1


async def test_no_title_kids_app_counts_under_app_key(parts):
    tracker, store = parts
    junior = dict(media_content_type="video", app_id="com.disney.junior", app_name="Disney Junior")
    await tracker.async_handle_state(TV, state("playing", **junior), at(0))
    await tracker.async_handle_state(TV, state("paused", **junior), at(300))
    seg = next(iter(store.segments.values()))
    assert seg.show_key == "app:com.disney.junior"
    assert build_summary(store, timezone.utc, at(400), 14, 1, 6)["today_minutes"] == 5


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


class GateResolver:
    """Holds one title's lookup open, the way a slow TMDB answer would."""

    def __init__(self, inner, slow_key, gate):
        self.inner, self.slow_key, self.gate = inner, slow_key, gate

    async def resolve(self, **kw):
        if kw["key"] == self.slow_key:
            await self.gate.wait()
        return await self.inner.resolve(**kw)


async def test_flush_does_not_double_count_a_tv_that_pauses_during_a_slow_lookup(hass):
    import asyncio

    store = ScreentimeStore(hass)
    await store.async_load()
    gate = asyncio.Event()
    tracker = SessionTracker(hass, store, GateResolver(ShowResolver(store, FakeTmdb()), "bluey", gate), [TV, "media_player.den_apple_tv"])
    peppa = dict(bluey(), media_series_title="Peppa Pig", media_title="Mud")
    den = State("media_player.den_apple_tv", "playing", peppa)
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state("media_player.den_apple_tv", den, at(0))
    flush = asyncio.create_task(tracker.async_flush(at(300)))
    await asyncio.sleep(0)
    await tracker.async_handle_state("media_player.den_apple_tv", State("media_player.den_apple_tv", "paused", peppa), at(330))
    gate.set()
    await flush
    assert [s.seconds for s in store.segments.values() if s.show_key == "peppa pig"] == [330]


class CountingTmdb(FakeTmdb):
    calls = 0

    async def lookup(self, title, media_type, year=None):
        type(self).calls += 1
        return await super().lookup(title, media_type, year)


async def test_ignored_app_is_dropped_before_any_lookup_or_show(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    tmdb = CountingTmdb()
    CountingTmdb.calls = 0
    tracker = SessionTracker(hass, store, ShowResolver(store, tmdb), [TV])
    yt = dict(bluey(), app_id="com.google.ios.youtube", app_name="YouTube")
    await tracker.async_handle_state(TV, state("playing", **yt), at(0))
    await tracker.async_handle_state(TV, state("paused", **yt), at(300))
    assert CountingTmdb.calls == 0 and not store.shows and not store.segments


async def test_same_title_in_youtube_does_not_change_earlier_totals(parts):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **bluey()), at(0))
    await tracker.async_handle_state(TV, state("paused", **bluey()), at(300))
    yt = dict(bluey(), app_id="com.google.ios.youtube", app_name="YouTube")
    await tracker.async_handle_state(TV, state("playing", **yt), at(400))
    await tracker.async_handle_state(TV, state("paused", **yt), at(700))
    assert store.shows["bluey"].verdict == Verdict.COUNT
    assert build_summary(store, timezone.utc, at(800), 14, 1, 6)["today_minutes"] == 5


async def test_apps_without_an_id_do_not_share_a_show_key(parts):
    tracker, store = parts
    for name in ("Disney Junior", "Hulu"):
        attrs = dict(media_content_type="video", app_name=name)
        await tracker.async_handle_state(TV, state("playing", **attrs), at(0))
        await tracker.async_handle_state(TV, state("paused", **attrs), at(300))
    assert {s.show_key for s in store.segments.values()} == {"app:disney junior", "app:hulu"}


# Real attributes read from the live house's recorder database (20 Nov 2026).
DISNEY = dict(app_id="com.disney.disneyplus", app_name="Disney+", media_title="How I Met Your Mother",
              media_artist="S1:E21 Milk", media_duration=1350, media_content_id="3a8c64c8")
CRAVE = dict(app_id="ca.bellmedia.cravetv", app_name="Crave", media_content_type="video", media_duration=1359,
             media_title="Friends ‑ S1 E5 The One With the East German Laundry Detergent", media_content_id="c1730780")
NETFLIX = dict(app_id="com.netflix.Netflix", app_name="Netflix")


async def watched(parts, attrs, seconds_=300):
    tracker, store = parts
    await tracker.async_handle_state(TV, state("playing", **attrs), at(0))
    await tracker.async_handle_state(TV, state("paused", **attrs), at(seconds_))
    return next(iter(store.segments.values()))


async def test_disney_plus_episode_is_read_from_the_artist_field(parts):
    seg = await watched(parts, DISNEY)
    assert (seg.series, seg.season, seg.episode, seg.show_key) == (
        "How I Met Your Mother", 1, 21, "how i met your mother")


async def test_crave_series_and_episode_are_read_from_the_title(parts):
    seg = await watched(parts, CRAVE)
    assert (seg.series, seg.season, seg.episode, seg.show_key) == ("Friends", 1, 5, "friends")


async def test_next_episode_of_the_same_show_starts_a_new_segment_under_one_show(parts):
    tracker, store = parts
    ep1, ep2 = dict(DISNEY), dict(DISNEY, media_artist="S1:E22 Come On", media_content_id="x2")
    await tracker.async_handle_state(TV, state("playing", **ep1), at(0))
    await tracker.async_handle_state(TV, state("playing", **ep2), at(300))
    await tracker.async_handle_state(TV, state("paused", **ep2), at(600))
    assert sorted((s.episode, s.seconds) for s in store.segments.values()) == [(21, 300), (22, 300)]
    assert {s.show_key for s in store.segments.values()} == {"how i met your mother"}


async def test_a_movie_and_an_app_with_no_details_keep_working(parts):
    movie = dict(DISNEY, media_title="Moana", media_artist="2016")
    seg = await watched(parts, movie)
    assert (seg.series, seg.season, seg.episode, seg.show_key) == (None, None, None, "moana")


async def test_netflix_reports_only_the_app_so_it_is_tracked_at_app_level(parts):
    seg = await watched(parts, NETFLIX)
    assert seg.show_key == "app:com.netflix.netflix" and seg.series is None and seg.duration_total is None
