from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kids_screentime.const import CONF_PLAYERS, CONF_WEEK_START, DOMAIN


async def setup_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_PLAYERS: [], CONF_WEEK_START: 6})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_panel_registered_admin_only(hass):
    await setup_entry(hass)
    panel = hass.data["frontend_panels"]["kids-screentime"]
    assert panel.require_admin is True
    assert panel.sidebar_title == "Kids Screentime"


async def test_panel_js_served(hass, hass_client):
    await setup_entry(hass)
    client = await hass_client()
    resp = await client.get("/kids_screentime_static/kids-screentime-panel.js")
    assert resp.status == 200
    assert "kids-screentime-panel" in await resp.text()


async def test_panel_removed_on_unload_and_back_on_reload(hass):
    entry = await setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "kids-screentime" not in hass.data["frontend_panels"]
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert "kids-screentime" in hass.data["frontend_panels"]
