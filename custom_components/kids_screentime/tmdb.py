"""Minimal TMDB client: age rating and kids genre for a title."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import aiohttp

from .models import show_key

BASE_URL = "https://api.themoviedb.org/3"
KIDS_GENRE_ID = 10762


class TmdbError(Exception):
    """TMDB could not be reached or refused the request."""


@dataclass(frozen=True)
class Lookup:
    tmdb_id: int
    rating: str | None
    kids_genre: bool
    exact: bool = True


class TmdbClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._key = api_key

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{BASE_URL}/{path}", params={"api_key": self._key, **params}
            ) as resp:
                if resp.status != 200:
                    raise TmdbError(f"TMDB {path} returned {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TmdbError(str(err)) from err

    async def validate(self) -> bool:
        try:
            await self._get("configuration")
        except TmdbError:
            return False
        return True

    async def lookup(
        self, title: str, media_type: Literal["tv", "movie"], year: int | None = None
    ) -> Lookup | None:
        params: dict[str, Any] = {"query": title}
        if year:
            params["first_air_date_year" if media_type == "tv" else "year"] = year
        results = (await self._get(f"search/{media_type}", **params)).get("results", [])
        if not results:
            return None
        wanted = show_key(title)
        name_field = "name" if media_type == "tv" else "title"
        exact_match = next((r for r in results if show_key(r.get(name_field, "")) == wanted), None)
        match = exact_match or results[0]
        tmdb_id = match["id"]
        details = await self._get(f"{media_type}/{tmdb_id}")
        kids_genre = any(g.get("id") == KIDS_GENRE_ID for g in details.get("genres", []))
        if media_type == "tv":
            rating = self._tv_rating(await self._get(f"tv/{tmdb_id}/content_ratings"))
        else:
            rating = self._movie_rating(await self._get(f"movie/{tmdb_id}/release_dates"))
        return Lookup(tmdb_id=tmdb_id, rating=rating, kids_genre=kids_genre, exact=exact_match is not None)

    @staticmethod
    def _tv_rating(data: dict[str, Any]) -> str | None:
        for entry in data.get("results", []):
            if entry.get("iso_3166_1") == "US":
                return entry.get("rating") or None
        return None

    @staticmethod
    def _movie_rating(data: dict[str, Any]) -> str | None:
        for entry in data.get("results", []):
            if entry.get("iso_3166_1") == "US":
                for release in entry.get("release_dates", []):
                    if release.get("certification"):
                        return release["certification"]
        return None
