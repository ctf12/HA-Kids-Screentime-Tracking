from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kids_screentime.const import CONF_PLAYERS, CONF_TMDB_KEY, CONF_WEEK_START, DOMAIN

INPUT = {CONF_PLAYERS: ["media_player.great_room_apple_tv"], CONF_WEEK_START: "6"}


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


async def test_flow_creates_entry(hass):
    with patch("custom_components.kids_screentime.async_setup_entry", return_value=True):
        form = await start(hass)
        assert form["type"] is FlowResultType.FORM
        done = await hass.config_entries.flow.async_configure(form["flow_id"], INPUT)
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"][CONF_PLAYERS] == ["media_player.great_room_apple_tv"]
    assert done["data"][CONF_WEEK_START] == 6


async def test_invalid_tmdb_key_shows_error(hass):
    form = await start(hass)
    with patch("custom_components.kids_screentime.config_flow.TmdbClient.validate", return_value=False):
        result = await hass.config_entries.flow.async_configure(form["flow_id"], {**INPUT, CONF_TMDB_KEY: "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_TMDB_KEY: "invalid_tmdb_key"}


async def test_valid_tmdb_key_is_stored(hass):
    form = await start(hass)
    with patch("custom_components.kids_screentime.config_flow.TmdbClient.validate", return_value=True), \
         patch("custom_components.kids_screentime.async_setup_entry", return_value=True):
        done = await hass.config_entries.flow.async_configure(form["flow_id"], {**INPUT, CONF_TMDB_KEY: "good"})
    assert done["data"][CONF_TMDB_KEY] == "good"


async def test_only_one_instance_allowed(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_PLAYERS: [], CONF_WEEK_START: 6}).add_to_hass(hass)
    result = await start(hass)
    assert result["type"] is FlowResultType.ABORT


async def test_options_update_reloads(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_PLAYERS: ["media_player.tv"], CONF_WEEK_START: 6})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.week_start == 6
    form = await hass.config_entries.options.async_init(entry.entry_id)
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], {CONF_PLAYERS: ["media_player.tv"], CONF_WEEK_START: "0"})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.week_start == 0
