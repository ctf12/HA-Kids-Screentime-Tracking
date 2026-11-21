"""Kids Screentime Tracking."""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import websocket_api
from .const import CONF_PLAYERS, CONF_TMDB_KEY, CONF_WEEK_START, DEFAULT_WEEK_START, DOMAIN
from .resolver import ShowResolver
from .runtime import RuntimeData
from .store import ScreentimeStore
from .tmdb import TmdbClient
from .tracker import SessionTracker

PLATFORMS = [Platform.SENSOR]
PANEL_URL = "kids-screentime"
STATIC_URL = "/kids_screentime_static"
PANEL_FILE = "kids-screentime-panel.js"


async def _register_panel(hass: HomeAssistant, domain_data: dict) -> None:
    if not domain_data.get("static"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(f"{STATIC_URL}/{PANEL_FILE}", str(Path(__file__).parent / "panel" / PANEL_FILE), False)]
        )
        domain_data["static"] = True
    await panel_custom.async_register_panel(
        hass, webcomponent_name="kids-screentime-panel", frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/{PANEL_FILE}", sidebar_title="Kids Screentime",
        sidebar_icon="mdi:television-play", require_admin=True,
    )


def _setting(entry: ConfigEntry, key: str, default=None):
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = ScreentimeStore(hass)
    await store.async_load()
    api_key = _setting(entry, CONF_TMDB_KEY)
    tmdb = TmdbClient(async_get_clientsession(hass), api_key) if api_key else None
    resolver = ShowResolver(store, tmdb)
    players = list(_setting(entry, CONF_PLAYERS, []))
    tracker = SessionTracker(hass, store, resolver, players)
    entry.runtime_data = RuntimeData(
        store=store, resolver=resolver, tracker=tracker, tz=ZoneInfo(hass.config.time_zone),
        week_start=int(_setting(entry, CONF_WEEK_START, DEFAULT_WEEK_START)),
    )
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("registered"):
        websocket_api.async_register(hass)
        websocket_api.async_register_services(hass)
        domain_data["registered"] = True
    await _register_panel(hass, domain_data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(tracker.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await entry.runtime_data.tracker.async_close_all(dt_util.utcnow())
    frontend.async_remove_panel(hass, PANEL_URL)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
