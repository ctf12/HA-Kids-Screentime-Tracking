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
                verdict=classify(key=key, app_name=app_name, rating=None, kids_genre=False, rules=self._store.rules),
                source="auto", lookup_failed=failed,
                first_seen=show.first_seen if show else now, last_seen=now,
            )
        show.verdict = classify(
            key=key, app_name=app_name, rating=show.rating,
            kids_genre=show.kids_genre, rules=self._store.rules,
        )
        show.last_seen = now
        if show.verdict == Verdict.DISCARD and key not in self._store.rules.never and key not in self._store.shows:
            return show  # adult viewing leaves no readable trace
        self._store.upsert_show(show)
        return show

    async def _lookup(self, key: str, title: str, media_type: str) -> tuple[Lookup | None, bool]:
        if self._tmdb is None or key.startswith("app:"):
            return None, False
        kinds = {"tvshow": ["tv"], "movie": ["movie"]}.get(media_type, ["tv", "movie"])
        for kind in kinds:
            cache_key = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:16]
            if cache_key in self._store.lookups:
                cached = self._store.lookups[cache_key]
                if cached is not None:
                    return Lookup(**cached), False
                continue
            try:
                found = await self._tmdb.lookup(title, kind)  # type: ignore[arg-type]
            except TmdbError:
                return None, True
            self._store.lookups[cache_key] = (
                None if found is None
                else {"tmdb_id": found.tmdb_id, "rating": found.rating, "kids_genre": found.kids_genre}
            )
            self._store.schedule_save()
            if found is not None:
                return found, False
        return None, False
