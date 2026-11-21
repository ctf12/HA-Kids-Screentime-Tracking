import pytest

from custom_components.kids_screentime.classifier import classify
from custom_components.kids_screentime.models import Rules, Verdict

C, D, R = Verdict.COUNT, Verdict.DISCARD, Verdict.REVIEW


@pytest.mark.parametrize(
    ("key", "app", "rating", "genre", "never", "always", "expected"),
    [
        ("bluey", "Disney+", "G", False, True, False, D),          # never beats rating G
        ("bluey", "Disney+", "TV-MA", False, False, True, C),      # always beats TV-MA
        ("x", "YouTube Kids", "TV-Y", False, False, False, D),     # YouTube ignored
        ("x", "Disney Junior", None, False, False, False, C),      # kids app
        ("x", "Disney+", "TV-Y7", False, False, False, C),
        ("x", "Disney+", "PG", False, False, False, C),
        ("x", "Disney+", "TV-PG", False, False, False, R),
        ("x", "Netflix", "TV-MA", False, False, False, D),
        ("x", "Netflix", "NR", False, False, False, R),
        ("x", "Netflix", None, True, False, False, C),
        ("x", "Netflix", None, False, False, False, R),
    ],
)
def test_classify(key, app, rating, genre, never, always, expected):
    rules = Rules()
    if never:
        rules.never.add(key)
    if always:
        rules.always.add(key)
    assert classify(key=key, app_name=app, rating=rating, kids_genre=genre, rules=rules) == expected
