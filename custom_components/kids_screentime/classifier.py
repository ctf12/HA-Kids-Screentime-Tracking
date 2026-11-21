"""Decide whether a title counts as kids' screen time."""
from __future__ import annotations

from .const import COUNT_RATINGS, DISCARD_RATINGS
from .models import Rules, Verdict


def _app_matches(app_name: str | None, names: set[str]) -> bool:
    if not app_name:
        return False
    folded = app_name.casefold()
    return any(name in folded for name in names)


def classify(
    *, key: str, app_name: str | None, rating: str | None, kids_genre: bool, rules: Rules
) -> Verdict:
    """First match wins: never, always, ignored app, kids app, rating, genre."""
    if key in rules.never:
        return Verdict.DISCARD
    if key in rules.always:
        return Verdict.COUNT
    if _app_matches(app_name, rules.ignored_apps):
        return Verdict.DISCARD
    if _app_matches(app_name, rules.kids_apps):
        return Verdict.COUNT
    if rating is not None:
        if rating in COUNT_RATINGS:
            return Verdict.COUNT
        if rating in DISCARD_RATINGS:
            return Verdict.DISCARD
        return Verdict.REVIEW
    return Verdict.COUNT if kids_genre else Verdict.REVIEW
