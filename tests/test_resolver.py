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
    assert junior.verdict == Verdict.COUNT


async def test_manual_never_beats_rating(store):
    resolver = ShowResolver(store, FakeTmdb())
    await resolve(resolver)
    store.set_rule("bluey", "never")
    assert (await resolve(resolver)).verdict == Verdict.DISCARD
