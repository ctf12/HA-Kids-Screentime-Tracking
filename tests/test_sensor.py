from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from custom_components.kids_screentime.models import Segment, Show, Verdict
from custom_components.kids_screentime.sensor import PendingSensor, TodaySensor, WeekSensor
from custom_components.kids_screentime.store import ScreentimeStore


@pytest.fixture
async def store(hass):
    s = ScreentimeStore(hass)
    await s.async_load()
    return s


def add(store, start, minutes, key="bluey", verdict=Verdict.COUNT, app="Disney+"):
    if key not in store.shows:
        store.upsert_show(Show(key, key.title(), "TV-Y", 1, True, verdict, "auto", False, start, start))
    store.add_segment(Segment(
        id=f"{key}-{start.isoformat()}", device="media_player.tv", app_id=None, app_name=app, title=key,
        series=key, season=None, episode=None, media_type="tvshow", show_key=key, start=start,
        end=start + timedelta(minutes=minutes), seconds=minutes * 60, position_max=None, duration_total=None,
    ))


NOW = "2026-11-20 12:00:00+00:00"


async def test_today_sensor_updates_when_segment_added(hass, store, freezer):
    freezer.move_to(NOW)
    sensor = TodaySensor(store, "entry1", ZoneInfo("UTC"), 6)
    assert sensor.native_value == 0
    now = datetime.now(timezone.utc)
    add(store, now - timedelta(minutes=30), 20)
    assert sensor.native_value == 20
    assert sensor.extra_state_attributes["by_app"] == {"Disney+": 20}
    assert sensor.extra_state_attributes["by_show"] == {"Bluey": 20}


async def test_pending_sensor_counts_review_minutes(hass, store, freezer):
    freezer.move_to(NOW)
    sensor = PendingSensor(store, "entry1")
    add(store, datetime.now(timezone.utc) - timedelta(minutes=30), 12, key="mystery", verdict=Verdict.REVIEW)
    assert sensor.native_value == 12


async def test_week_sensor_includes_today(hass, store, freezer):
    freezer.move_to(NOW)
    sensor = WeekSensor(store, "entry1", ZoneInfo("UTC"), 6)
    add(store, datetime.now(timezone.utc) - timedelta(minutes=30), 25)
    assert sensor.native_value == 25
