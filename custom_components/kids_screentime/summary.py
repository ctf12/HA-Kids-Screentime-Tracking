"""Aggregate stored segments into daily and weekly totals and breakdowns."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from .models import Segment, Verdict
from .store import ScreentimeStore


def _minutes(seconds: float) -> int:
    return round(seconds / 60)


def split_by_day(seg: Segment, tz: tzinfo) -> dict[date, float]:
    """Seconds of a segment that fall on each local calendar day."""
    start, end = seg.start.astimezone(tz), seg.end.astimezone(tz)
    out: dict[date, float] = {}
    cursor = start
    while cursor < end:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=tz)
        stop = min(end, next_midnight)
        out[cursor.date()] = out.get(cursor.date(), 0.0) + (stop - cursor).total_seconds()
        cursor = stop
    return out


def week_start_date(day: date, week_start: int) -> date:
    return day - timedelta(days=(day.weekday() - week_start) % 7)


def _counted(store: ScreentimeStore):
    for seg in store.segments.values():
        show = store.shows.get(seg.show_key)
        if show and show.verdict == Verdict.COUNT:
            yield seg, show


def pending_minutes(store: ScreentimeStore) -> int:
    total = 0.0
    for seg in store.segments.values():
        show = store.shows.get(seg.show_key)
        if show and show.verdict == Verdict.REVIEW:
            total += (seg.end - seg.start).total_seconds()
    return _minutes(total)


def breakdown(
    store: ScreentimeStore, tz: tzinfo, first: date, last: date
) -> tuple[dict[str, int], dict[str, int]]:
    """Minutes by app name and by show title for local days first..last."""
    apps: dict[str, float] = defaultdict(float)
    shows: dict[str, float] = defaultdict(float)
    for seg, show in _counted(store):
        seconds = sum(s for d, s in split_by_day(seg, tz).items() if first <= d <= last)
        if seconds:
            apps[seg.app_name or "Unknown app"] += seconds
            shows[show.title] += seconds
    return {k: _minutes(v) for k, v in apps.items()}, {k: _minutes(v) for k, v in shows.items()}


def build_summary(
    store: ScreentimeStore, tz: tzinfo, now: datetime, days: int, weeks: int, week_start: int
) -> dict[str, Any]:
    today = now.astimezone(tz).date()
    day_seconds: dict[date, float] = defaultdict(float)
    for seg, _show in _counted(store):
        for d, s in split_by_day(seg, tz).items():
            day_seconds[d] += s

    first_day = today - timedelta(days=days - 1)
    day_list = [first_day + timedelta(days=i) for i in range(days)]
    this_week = week_start_date(today, week_start)
    week_list = [this_week - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]

    apps: dict[str, float] = defaultdict(float)
    shows: dict[str, dict[str, Any]] = {}
    for seg, show in _counted(store):
        in_window = sum(s for d, s in split_by_day(seg, tz).items() if first_day <= d <= today)
        entry = shows.setdefault(show.key, {"title": show.title, "seconds": 0.0, "percent": None})
        if seg.position_max is not None and seg.duration_total:
            pct = round(100 * min(1.0, seg.position_max / seg.duration_total))
            entry["percent"] = max(entry["percent"] or 0, pct)
        if in_window:
            apps[seg.app_name or "Unknown app"] += in_window
            entry["seconds"] += in_window

    return {
        "today_minutes": _minutes(day_seconds.get(today, 0.0)),
        "pending_minutes": pending_minutes(store),
        "week_start": week_start,
        "days": [{"date": d.isoformat(), "minutes": _minutes(day_seconds.get(d, 0.0))} for d in day_list],
        "weeks": [
            {
                "start": w.isoformat(),
                "minutes": _minutes(sum(day_seconds.get(w + timedelta(days=i), 0.0) for i in range(7))),
            }
            for w in week_list
        ],
        "apps": [
            {"app": name, "minutes": _minutes(sec)}
            for name, sec in sorted(apps.items(), key=lambda kv: -kv[1])
        ],
        "shows": [
            {"key": key, "title": e["title"], "minutes": _minutes(e["seconds"]), "percent": e["percent"]}
            for key, e in sorted(shows.items(), key=lambda kv: -kv[1]["seconds"])
            if e["seconds"]
        ],
    }
