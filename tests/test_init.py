from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kids_screentime.const import CONF_PLAYERS, CONF_TMDB_KEY, CONF_WEEK_START, DOMAIN, SIGNAL_UPDATED
from custom_components.kids_screentime.models import Segment, Show, Verdict


def entry(**extra):
    return MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN,
        data={CONF_PLAYERS: ["media_player.great_room_apple_tv"], CONF_WEEK_START: 6, **extra})


async def test_setup_and_unload_cleanly(hass):
    e = entry()
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    assert e.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.kids_screentime_today") is not None
    assert hass.states.get("sensor.kids_screentime_this_week") is not None
    assert hass.states.get("sensor.kids_screentime_pending_review") is not None
    assert await hass.config_entries.async_unload(e.entry_id)
    assert e.state is ConfigEntryState.NOT_LOADED


async def test_setup_without_tmdb_key_works(hass):
    e = entry()
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    assert CONF_TMDB_KEY not in e.data
    assert e.runtime_data.resolver is not None


async def test_sensor_state_follows_store(hass, freezer):
    freezer.move_to("2026-11-20 12:00:00+00:00")
    e = entry()
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    store = e.runtime_data.store
    start = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
    store.upsert_show(Show("bluey", "Bluey", "TV-Y", 1, True, Verdict.COUNT, "auto", False, start, start))
    store.add_segment(Segment(
        id="s", device="media_player.tv", app_id=None, app_name="Disney+", title="Bluey", series="Bluey",
        season=None, episode=None, media_type="tvshow", show_key="bluey", start=start,
        end=start + timedelta(minutes=20), seconds=1200, position_max=None, duration_total=None))
    async_dispatcher_send(hass, SIGNAL_UPDATED)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kids_screentime_today").state == "20"
