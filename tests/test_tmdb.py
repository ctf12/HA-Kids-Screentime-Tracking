import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.kids_screentime.tmdb import Lookup, TmdbClient, TmdbError

BASE = "https://api.themoviedb.org/3"


@pytest.fixture
def client(hass, aioclient_mock):
    return TmdbClient(async_get_clientsession(hass), "KEY"), aioclient_mock


async def test_tv_lookup_returns_us_rating(client):
    c, mock = client
    mock.get(f"{BASE}/search/tv", json={"results": [{"id": 82728, "name": "Bluey"}]})
    mock.get(f"{BASE}/tv/82728/content_ratings", json={"results": [
        {"iso_3166_1": "GB", "rating": "U"}, {"iso_3166_1": "US", "rating": "TV-Y7"}]})
    mock.get(f"{BASE}/tv/82728", json={"genres": [{"id": 10762, "name": "Kids"}]})
    assert await c.lookup("Bluey", "tv") == Lookup(tmdb_id=82728, rating="TV-Y7", kids_genre=True)


async def test_movie_lookup_returns_us_certification(client):
    c, mock = client
    mock.get(f"{BASE}/search/movie", json={"results": [{"id": 277834, "title": "Moana"}]})
    mock.get(f"{BASE}/movie/277834/release_dates", json={"results": [
        {"iso_3166_1": "US", "release_dates": [{"certification": ""}, {"certification": "PG"}]}]})
    mock.get(f"{BASE}/movie/277834", json={"genres": [{"id": 16, "name": "Animation"}]})
    assert await c.lookup("Moana", "movie", 2016) == Lookup(tmdb_id=277834, rating="PG", kids_genre=False)


async def test_no_results_returns_none(client):
    c, mock = client
    mock.get(f"{BASE}/search/tv", json={"results": []})
    assert await c.lookup("Nothing Here", "tv") is None


async def test_http_500_raises_tmdb_error(client):
    c, mock = client
    mock.get(f"{BASE}/search/tv", status=500)
    with pytest.raises(TmdbError):
        await c.lookup("Bluey", "tv")


async def test_401_raises_tmdb_error_and_validate_false(client):
    c, mock = client
    mock.get(f"{BASE}/search/tv", status=401)
    mock.get(f"{BASE}/configuration", status=401)
    with pytest.raises(TmdbError):
        await c.lookup("Bluey", "tv")
    assert await c.validate() is False


async def test_only_title_and_year_are_sent(client):
    c, mock = client
    mock.get(f"{BASE}/search/movie", json={"results": []})
    await c.lookup("Moana", "movie", 2016)
    url = mock.mock_calls[0][1]
    assert dict(url.query) == {"api_key": "KEY", "query": "Moana", "year": "2016"}


async def test_loose_match_is_flagged_not_exact(client):
    c, mock = client
    mock.get(f"{BASE}/search/tv", json={"results": [{"id": 5, "name": "Something Else"}]})
    mock.get(f"{BASE}/tv/5/content_ratings", json={"results": [{"iso_3166_1": "US", "rating": "TV-14"}]})
    mock.get(f"{BASE}/tv/5", json={"genres": []})
    found = await c.lookup("Bluey", "tv")
    assert found is not None and found.exact is False
