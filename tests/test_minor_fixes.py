import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import Context, State
from homeassistant.exceptions import Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kids_screentime.const import CONF_PLAYERS, CONF_TMDB_KEY, CONF_WEEK_START, DOMAIN
from custom_components.kids_screentime.models import Segment, Show, Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.summary import build_summary
from custom_components.kids_screentime.tmdb import Lookup, TmdbClient, TmdbError
from custom_components.kids_screentime.tracker import SessionTracker

UTC = timezone.utc
TV = "media_player.great_room_apple_tv"
T0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)


def entry(**extra):
    return MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_PLAYERS: [TV], CONF_WEEK_START: 6, **extra})


async def setup(hass, **extra):
    e = entry(**extra)
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    return e


def show(key="bluey", verdict=Verdict.COUNT, source="auto"):
    return Show(key, key.title(), "TV-Y", 1, True, verdict, source, False, T0, T0)


# M-1
async def test_services_are_admin_only(hass, hass_read_only_user, hass_admin_user):
    e = await setup(hass)
    e.runtime_data.store.upsert_show(show())
    ctx = Context(user_id=hass_read_only_user.id)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "delete_show", {"key": "bluey"}, blocking=True, context=ctx)
    await hass.services.async_call(
        DOMAIN, "delete_show", {"key": "bluey"}, blocking=True, context=Context(user_id=hass_admin_user.id))
    assert "bluey" in e.runtime_data.store.rules.never


# M-2
async def test_repeated_dst_hour_counts_real_elapsed_time(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    start = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)  # 01:00 CDT; the clocks then repeat 01:00-02:00
    store.upsert_show(show())
    store.add_segment(Segment("d", TV, None, "Disney+", "Bluey", "Bluey", None, None, "tvshow", "bluey",
                              start, start + timedelta(hours=2), 7200, None, None))
    by_day = {d["date"]: d["minutes"] for d in build_summary(
        store, ZoneInfo("America/Chicago"), datetime(2026, 11, 20, 18, tzinfo=UTC), 30, 1, 6)["days"]}
    assert by_day["2026-11-01"] == 120


# M-3
async def test_tmdb_key_can_be_removed_in_options(hass):
    e = await setup(hass, **{CONF_TMDB_KEY: "oldkey"})
    assert e.runtime_data.resolver.has_tmdb is True
    form = await hass.config_entries.options.async_init(e.entry_id)
    await hass.config_entries.options.async_configure(form["flow_id"], {CONF_PLAYERS: [TV], CONF_WEEK_START: "6"})
    await hass.async_block_till_done()
    assert e.runtime_data.resolver.has_tmdb is False


# M-7
class GateTmdb:
    def __init__(self):
        self.gate = asyncio.Event()

    async def lookup(self, title, media_type, year=None):
        await self.gate.wait()
        return Lookup(1, "TV-Y", True)


async def test_manual_decision_survives_an_in_flight_lookup(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    tmdb = GateTmdb()
    task = asyncio.create_task(ShowResolver(store, tmdb).resolve(key="bluey", title="Bluey", media_type="tvshow", app_name="Disney+"))
    await asyncio.sleep(0)
    store.upsert_show(show(verdict=Verdict.REVIEW))
    store.resolve_review("bluey", True)
    tmdb.gate.set()
    result = await task
    assert result.source == "manual" and store.shows["bluey"].source == "manual"


# M-8
class _Resp:
    status = 200

    async def json(self):
        return {"results": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Session:
    def get(self, url, **kw):
        self.kw = kw
        return _Resp()


async def test_tmdb_requests_have_a_timeout():
    session = _Session()
    await TmdbClient(session, "K").lookup("x", "tv")
    assert session.kw["timeout"].total == 10


# M-9
async def test_bad_media_position_does_not_lose_the_segment(hass):
    store = ScreentimeStore(hass)
    await store.async_load()
    tracker = SessionTracker(hass, store, ShowResolver(store, None), [TV])
    attrs = dict(media_content_type="tvshow", media_series_title="Bluey", app_id="com.disney.disneyplus",
                 app_name="Disney+", media_position="oops", media_duration="bad")
    await tracker.async_handle_state(TV, State(TV, "playing", attrs), T0)
    await tracker.async_handle_state(TV, State(TV, "paused", attrs), T0 + timedelta(seconds=300))
    seg = next(iter(store.segments.values()))
    assert seg.seconds == 300 and seg.position_max is None and seg.duration_total is None


# M-10
async def test_set_show_rule_without_rule_unblocks(hass):
    e = await setup(hass)
    e.runtime_data.store.delete_show("bluey")
    await hass.services.async_call(DOMAIN, "set_show_rule", {"key": "bluey"}, blocking=True)
    assert "bluey" not in e.runtime_data.store.rules.never


# M-12
async def test_time_zone_change_reloads_the_entry(hass):
    e = await setup(hass)
    await hass.config.async_update(time_zone="America/Chicago")
    await hass.async_block_till_done()
    assert e.runtime_data.tz == ZoneInfo("America/Chicago")


# M-14
async def test_tmdb_failure_is_logged_without_the_title(hass, caplog):
    class Down:
        async def lookup(self, *a, **k):
            raise TmdbError("TMDB search/tv returned 401")

    store = ScreentimeStore(hass)
    await store.async_load()
    with caplog.at_level(logging.WARNING):
        await ShowResolver(store, Down()).resolve(key="bluey", title="Bluey", media_type="tvshow", app_name=None)
    assert "TMDB lookup failed" in caplog.text and "Bluey" not in caplog.text
