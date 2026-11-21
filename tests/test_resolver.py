from datetime import datetime, timezone

import pytest

from custom_components.kids_screentime.models import Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.tmdb import Lookup, TmdbError

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


class FakeTmdb:
    def __init__(self, results=None, fail_times=0):
        self.results = results or {"bluey": Lookup(1, "TV-Y", True)}
        self.fail_times = fail_times
        self.calls = 0

    async def lookup(self, title, media_type, year=None):
        self.calls += 1
        if self.fail_times:
            self.fail_times -= 1
            raise TmdbError("down")
        return self.results.get(title.casefold())


@pytest.fixture
async def store(hass):
    s = ScreentimeStore(hass)
    await s.async_load()
    return s


async def resolve(resolver, key="bluey", title="Bluey", app="Disney+", media_type="tvshow"):
    return await resolver.resolve(key=key, title=title, media_type=media_type, app_name=app, now=NOW)


async def test_second_resolve_uses_cache(store):
    tmdb = FakeTmdb()
    resolver = ShowResolver(store, tmdb)
    first = await resolve(resolver)
    second = await resolve(resolver)
    assert first.verdict == second.verdict == Verdict.COUNT
    assert tmdb.calls == 1


async def test_tmdb_error_gives_review_and_retries_next_time(store):
    tmdb = FakeTmdb(fail_times=1)
    resolver = ShowResolver(store, tmdb)
    first = await resolve(resolver)
    assert first.verdict == Verdict.REVIEW and first.lookup_failed
    second = await resolve(resolver)
    assert second.verdict == Verdict.COUNT and not second.lookup_failed
    assert tmdb.calls == 2


async def test_no_tmdb_key_uses_rules_and_app_only(store):
    resolver = ShowResolver(store, None)
    assert (await resolve(resolver, app="Netflix")).verdict == Verdict.REVIEW
    junior = await resolve(resolver, key="app:x", title="Disney Junior", app="Disney Junior")
    assert junior.verdict == Verdict.REVIEW  # kids' apps are decided per segment, not per show


async def test_manual_never_beats_rating(store):
    resolver = ShowResolver(store, FakeTmdb())
    await resolve(resolver)
    store.set_rule("bluey", "never")
    assert (await resolve(resolver)).verdict == Verdict.DISCARD


async def test_discarded_adult_title_leaves_no_trace(store):
    tmdb = FakeTmdb({"gritty drama": Lookup(9, "TV-MA", False)})
    resolver = ShowResolver(store, tmdb)
    shown = await resolve(resolver, key="gritty drama", title="Gritty Drama", app="Netflix")
    assert shown.verdict == Verdict.DISCARD
    assert "gritty drama" not in store.shows
    assert not any("gritty" in k for k in store.lookups)
    again = await resolve(resolver, key="gritty drama", title="Gritty Drama", app="Netflix")
    assert again.verdict == Verdict.DISCARD
    assert tmdb.calls == 1  # still cached, just not readable


async def test_no_key_marks_titles_for_retry_and_a_later_key_resolves_them(store):
    first = await resolve(ShowResolver(store, None), app="Netflix")
    assert first.verdict == Verdict.REVIEW and first.lookup_failed
    later = await resolve(ShowResolver(store, FakeTmdb()), app="Netflix")
    assert later.verdict == Verdict.COUNT and not later.lookup_failed


async def test_review_title_that_turns_adult_is_purged(store):
    from datetime import timedelta

    from custom_components.kids_screentime.models import Segment

    flaky = FakeTmdb({"gritty drama": Lookup(9, "TV-MA", False)}, fail_times=1)
    resolver = ShowResolver(store, flaky)
    await resolve(resolver, key="gritty drama", title="Gritty Drama", app="Netflix")
    store.add_segment(Segment("g1", "media_player.tv", None, "Netflix", "Gritty Drama", None, None, None, "tvshow",
                              "gritty drama", NOW, NOW + timedelta(minutes=5), 300, None, None))
    await resolve(resolver, key="gritty drama", title="Gritty Drama", app="Netflix")
    assert "gritty drama" not in store.shows and not store.segments


async def test_loose_match_never_discards(store):
    loose = Lookup(7, "TV-14", False, exact=False)
    shown = await resolve(ShowResolver(store, FakeTmdb({"bluey": loose})))
    assert shown.verdict == Verdict.REVIEW and "bluey" in store.shows
