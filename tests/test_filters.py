from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from custom_components.kids_screentime.filters import kept_intervals, validate_window
from custom_components.kids_screentime.models import QuietWindow

UTC = timezone.utc
CHI = ZoneInfo("America/Chicago")
WED = 2


def at(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=UTC)  # 18 Nov 2026 is a Wednesday


def window(**kw):
    base = dict(id="w1", apps=["netflix"], days=[WED], start="21:00", end="23:00")
    return QuietWindow(**{**base, **kw})


def test_no_windows_keeps_the_whole_segment():
    assert kept_intervals(at(18, 20), at(18, 22), "Netflix", [], UTC) == [(at(18, 20), at(18, 22))]


def test_a_window_removes_only_its_overlap():
    assert kept_intervals(at(18, 20, 30), at(18, 22, 30), "Netflix", [window()], UTC) == [(at(18, 20, 30), at(18, 21))]


def test_a_segment_fully_inside_a_window_leaves_nothing():
    assert kept_intervals(at(18, 21, 30), at(18, 22), "Netflix", [window()], UTC) == []


def test_a_window_on_other_days_does_not_apply():
    thursday = kept_intervals(at(19, 21, 30), at(19, 22), "Netflix", [window()], UTC)
    assert thursday == [(at(19, 21, 30), at(19, 22))]


def test_a_window_for_another_app_does_not_apply():
    assert kept_intervals(at(18, 21, 30), at(18, 22), "Disney+", [window()], UTC) == [(at(18, 21, 30), at(18, 22))]


def test_no_apps_listed_means_every_app():
    assert kept_intervals(at(18, 21, 30), at(18, 22), "Disney+", [window(apps=[])], UTC) == []


def test_app_names_match_loosely_like_the_kids_app_list():
    assert kept_intervals(at(18, 21, 30), at(18, 22), "Netflix", [window(apps=["NETFLIX"])], UTC) == []


def test_a_window_that_crosses_midnight_belongs_to_the_day_it_starts():
    overnight = window(start="22:00", end="06:00")
    assert kept_intervals(at(19, 0, 30), at(19, 1, 30), "Netflix", [overnight], UTC) == []  # Thu 00:30 is Wed night
    assert kept_intervals(at(18, 21), at(18, 23), "Netflix", [overnight], UTC) == [(at(18, 21), at(18, 22))]
    assert kept_intervals(at(19, 23), at(19, 23, 30), "Netflix", [overnight], UTC) == [(at(19, 23), at(19, 23, 30))]


def test_times_are_the_local_wall_clock():
    start, end = datetime(2026, 11, 19, 2, 30, tzinfo=UTC), datetime(2026, 11, 19, 4, 30, tzinfo=UTC)  # Wed 20:30-22:30 CST
    kept = kept_intervals(start, end, "Netflix", [window()], CHI)
    assert kept == [(start, datetime(2026, 11, 19, 3, 0, tzinfo=UTC))]  # 21:00 CST is 03:00 UTC


def test_overlapping_windows_do_not_double_remove():
    ws = [window(id="a", start="21:00", end="22:30"), window(id="b", start="22:00", end="23:00")]
    assert kept_intervals(at(18, 20), at(18, 23, 30), "Netflix", ws, UTC) == [(at(18, 20), at(18, 21)), (at(18, 23), at(18, 23, 30))]


@pytest.mark.parametrize("days,start,end", [([], "21:00", "23:00"), ([2], "9pm", "23:00"), ([2], "21:00", "21:00"), ([7], "21:00", "23:00"), ([2], "25:00", "23:00")])
def test_validation_rejects_bad_windows(days, start, end):
    with pytest.raises(ValueError):
        validate_window(days, start, end)


def test_validation_accepts_a_good_window():
    validate_window([2, 4], "21:30", "06:00")
