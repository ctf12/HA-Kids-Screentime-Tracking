"""Turn a title into a Show with a verdict, using TMDB, the cache and the rules."""
from __future__ import annotations

import hashlib
from datetime import datetime

from homeassistant.util import dt as dt_util

from .classifier import classify
from .models import Show, Verdict
from .store import ScreentimeStore
from .tmdb import Lookup, TmdbClient, TmdbError


class ShowResolver:
    """App rules (ignored and kids' apps) are decided per segment by the tracker and the store,
    so a show's verdict here depends only on the title, its rating and the user's lists."""

    def __init__(self, store: ScreentimeStore, tmdb: TmdbClient | None) -> None:
        self._store = store
        self._tmdb = tmdb

    async def resolve(
        self, *, key: str, title: str, media_type: str, app_name: str | None,
        now: datetime | None = None,
    ) -> Show:
        now = now or dt_util.utcnow()
        show = self._store.shows.get(key)
        if show is None or show.lookup_failed:
            lookup, failed = await self._lookup(key, title, media_type)
            show = Show(
                key=key, title=title,
                rating=lookup.rating if lookup else None,
                tmdb_id=lookup.tmdb_id if lookup else None,
                kids_genre=lookup.kids_genre if lookup else False,
                verdict=Verdict.REVIEW, source="auto", lookup_failed=failed,
                first_seen=show.first_seen if show else now, last_seen=now,
                exact=lookup.exact if lookup else True,
            )
        verdict = classify(
            key=key, app_name=None, rating=show.rating, kids_genre=show.kids_genre, rules=self._store.rules)
        if verdict == Verdict.DISCARD and not show.exact and key not in self._store.rules.never:
            verdict = Verdict.REVIEW  # a loose title match must never silently discard
        show.verdict = verdict
        show.last_seen = now
        if verdict == Verdict.DISCARD and key not in self._store.rules.never:
            self._store.purge_show(key)  # adult viewing leaves no trace, even if it was in review before
            return show
        self._store.upsert_show(show)
        return show

    async def _lookup(self, key: str, title: str, media_type: str) -> tuple[Lookup | None, bool]:
        if key.startswith("app:"):
            return None, False
        if self._tmdb is None:
            return None, True  # no key yet: retried once one is added
        kinds = {"tvshow": ["tv"], "movie": ["movie"]}.get(media_type, ["tv", "movie"])
        loose: Lookup | None = None
        for kind in kinds:
            found, failed = await self._lookup_kind(kind, key, title)
            if failed:
                return None, True
            if found is None:
                continue
            if found.exact:
                return found, False
            loose = loose or found
        return loose, False

    async def _lookup_kind(self, kind: str, key: str, title: str) -> tuple[Lookup | None, bool]:
        cache_key = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:16]
        if cache_key in self._store.lookups:
            cached = self._store.lookups[cache_key]
            return (Lookup(**cached) if cached is not None else None), False
        try:
            found = await self._tmdb.lookup(title, kind)  # type: ignore[union-attr,arg-type]
        except TmdbError:
            return None, True
        self._store.lookups[cache_key] = (
            None if found is None else {
                "tmdb_id": found.tmdb_id, "rating": found.rating,
                "kids_genre": found.kids_genre, "exact": found.exact,
            }
        )
        self._store.schedule_save()
        return found, False
