from datetime import datetime, timezone

import pytest

from custom_components.kids_screentime.models import Segment, Show, Verdict, show_key
from custom_components.kids_screentime.store import ScreentimeStore

T0 = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def make_segment(seg_id="s1", key="bluey", seconds=600):
    return Segment(
        id=seg_id, device="media_player.great_room_apple_tv", app_id="com.disney.disneyplus",
        app_name="Disney+", title="Bluey", series="Bluey", season=1, episode=2, media_type="tvshow",
        show_key=key, start=T0, end=T0, seconds=seconds, position_max=300.0, duration_total=420.0,
    )


def make_show(key="bluey", verdict=Verdict.COUNT):
    return Show(
        key=key, title="Bluey", rating="TV-Y", tmdb_id=1, kids_genre=True, verdict=verdict,
        source="auto", lookup_failed=False, first_seen=T0, last_seen=T0,
    )


@pytest.fixture
async def store(hass):
    s = ScreentimeStore(hass)
    await s.async_load()
    return s


def test_show_key_normalizes():
    assert show_key("Bluey (2018)") == "bluey"
    assert show_key("  bluey ") == "bluey"


async def test_round_trip_save_load(hass, store):
    store.upsert_show(make_show())
    store.add_segment(make_segment())
    await store.async_save()
    again = ScreentimeStore(hass)
    await again.async_load()
    assert again.shows["bluey"] == make_show()
    assert again.segments["s1"] == make_segment()


async def test_delete_show_removes_segments_and_blocks(store):
    store.upsert_show(make_show())
    store.add_segment(make_segment("s1"))
    store.add_segment(make_segment("s2"))
    assert store.delete_show("bluey") == 2
    assert not store.segments
    assert "bluey" in store.rules.never


async def test_resolve_review_count_false_removes_segments(store):
    store.upsert_show(make_show(verdict=Verdict.REVIEW))
    store.add_segment(make_segment())
    store.resolve_review("bluey", False)
    assert not store.segments
    assert "bluey" in store.rules.never


async def test_resolve_review_count_true_sets_always(store):
    store.upsert_show(make_show(verdict=Verdict.REVIEW))
    store.add_segment(make_segment())
    store.resolve_review("bluey", True)
    assert store.shows["bluey"].verdict == Verdict.COUNT
    assert "bluey" in store.rules.always
    assert len(store.segments) == 1


async def test_delete_segment_unknown_returns_false(store):
    assert store.delete_segment("nope") is False
