from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from custom_components.kids_screentime.models import Segment, Show, Verdict
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.summary import build_summary

UTC = timezone.utc
CHI = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)  # a Friday


@pytest.fixture
async def store(hass):
    s = ScreentimeStore(hass)
    await s.async_load()
    return s


def add(store, start, minutes, key="bluey", verdict=Verdict.COUNT, app="Disney+", seg_id=None, pos=None):
    if key not in store.shows:
        store.upsert_show(Show(key, key.title(), "TV-Y", 1, True, verdict, "auto", False, start, start))
    end = start + timedelta(minutes=minutes)
    store.add_segment(Segment(
        id=seg_id or f"{key}-{start.isoformat()}", device="media_player.tv", app_id=None, app_name=app,
        title=key, series=key, season=None, episode=None, media_type="tvshow", show_key=key,
        start=start, end=end, seconds=minutes * 60, position_max=pos, duration_total=100 if pos else None,
    ))


def summary(store, tz=UTC, days=14, weeks=12, week_start=6):
    return build_summary(store, tz, NOW, days, weeks, week_start)


async def test_midnight_spanning_segment_splits_across_days(store):
    add(store, datetime(2026, 11, 19, 23, 50, tzinfo=UTC), 30)
    by_day = {d["date"]: d["minutes"] for d in summary(store)["days"]}
    assert by_day["2026-11-19"] == 10 and by_day["2026-11-20"] == 20


async def test_week_buckets_start_on_configured_day(store):
    add(store, datetime(2026, 11, 15, 12, 0, tzinfo=UTC), 30)  # Sunday
    sunday = summary(store, weeks=2, week_start=6)["weeks"]
    monday = summary(store, weeks=2, week_start=0)["weeks"]
    assert [w["start"] for w in sunday] == ["2026-11-08", "2026-11-15"]
    assert [w["minutes"] for w in sunday] == [0, 30]
    assert [w["start"] for w in monday] == ["2026-11-09", "2026-11-16"]
    assert [w["minutes"] for w in monday] == [30, 0]


async def test_pending_excluded_from_totals_but_reported(store):
    add(store, datetime(2026, 11, 20, 10, 0, tzinfo=UTC), 10, key="mystery", verdict=Verdict.REVIEW)
    s = summary(store)
    assert s["today_minutes"] == 0 and s["pending_minutes"] == 10 and not s["shows"]


async def test_review_approval_moves_pending_into_totals(store):
    add(store, datetime(2026, 11, 20, 10, 0, tzinfo=UTC), 10, key="mystery", verdict=Verdict.REVIEW)
    store.resolve_review("mystery", True)
    s = summary(store)
    assert s["today_minutes"] == 10 and s["pending_minutes"] == 0


async def test_discarded_show_never_counts(store):
    add(store, datetime(2026, 11, 20, 10, 0, tzinfo=UTC), 10, verdict=Verdict.DISCARD)
    assert summary(store)["today_minutes"] == 0


async def test_arrays_zero_filled_and_oldest_first(store):
    s = summary(store)
    assert len(s["days"]) == 14 and len(s["weeks"]) == 12
    assert s["days"][0]["date"] == "2026-11-07" and s["days"][-1]["date"] == "2026-11-20"
    assert all(d["minutes"] == 0 for d in s["days"])
    assert s["week_start"] == 6


async def test_dst_day_uses_local_dates(store):
    add(store, datetime(2026, 11, 1, 4, 30, tzinfo=UTC), 120)  # 23:30 CDT Oct 31 -> 01:30 CDT Nov 1
    by_day = {d["date"]: d["minutes"] for d in summary(store, tz=CHI, days=30)["days"]}
    assert by_day["2026-10-31"] == 30 and by_day["2026-11-01"] == 90


async def test_apps_and_shows_breakdown_largest_first(store):
    add(store, datetime(2026, 11, 20, 9, 0, tzinfo=UTC), 20, key="bluey", app="Disney+", pos=50)
    add(store, datetime(2026, 11, 20, 10, 0, tzinfo=UTC), 40, key="moana", app="Disney+", pos=100)
    add(store, datetime(2026, 11, 19, 10, 0, tzinfo=UTC), 15, key="pbs", app="PBS Kids")
    s = summary(store)
    assert s["apps"] == [{"app": "Disney+", "minutes": 60}, {"app": "PBS Kids", "minutes": 15}]
    assert [x["key"] for x in s["shows"]] == ["moana", "bluey", "pbs"]
    assert [x["percent"] for x in s["shows"]] == [100, 50, None]
