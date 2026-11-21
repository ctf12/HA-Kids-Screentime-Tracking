"""Quiet windows: hours and weekdays whose viewing is disregarded (still logged, never counted)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from .classifier import app_matches
from .models import QuietWindow

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _parse(value: str) -> time:
    m = _HHMM.match(value)
    if not m:
        raise ValueError(f"time must be HH:MM, got {value!r}")
    return time(int(m.group(1)), int(m.group(2)))


def validate_window(days: list[int], start: str, end: str) -> None:
    if not days or any(not isinstance(d, int) or not 0 <= d <= 6 for d in days):
        raise ValueError("Pick at least one day of the week.")
    if _parse(start) == _parse(end):
        raise ValueError("start and end must differ")


def _applies(window: QuietWindow, app_name: str | None) -> bool:
    return not window.apps or app_matches(app_name, {a.casefold() for a in window.apps})


def _blocked(windows: list[QuietWindow], first: date, last: date, tz: tzinfo) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    day = first
    while day <= last:
        for w in windows:
            if day.weekday() not in w.days:
                continue
            start_t, end_t = _parse(w.start), _parse(w.end)
            end_day = day if end_t > start_t else day + timedelta(days=1)
            out.append((
                datetime.combine(day, start_t, tzinfo=tz).astimezone(timezone.utc),
                datetime.combine(end_day, end_t, tzinfo=tz).astimezone(timezone.utc),
            ))
        day += timedelta(days=1)
    return sorted(out)


def kept_intervals(
    start: datetime, end: datetime, app_name: str | None, windows: list[QuietWindow], tz: tzinfo
) -> list[tuple[datetime, datetime]]:
    """The parts of [start, end] that still count after removing every applicable quiet window."""
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    applicable = [w for w in windows if _applies(w, app_name)]
    if not applicable or end <= start:
        return [(start, end)]
    first = start.astimezone(tz).date() - timedelta(days=1)  # an overnight window starts the day before
    last = end.astimezone(tz).date()
    kept, cursor = [], start
    for b_start, b_end in _blocked(applicable, first, last, tz):
        if b_end <= cursor or b_start >= end:
            continue
        if b_start > cursor:
            kept.append((cursor, b_start))
        cursor = max(cursor, b_end)
        if cursor >= end:
            break
    if cursor < end:
        kept.append((cursor, end))
    return kept
