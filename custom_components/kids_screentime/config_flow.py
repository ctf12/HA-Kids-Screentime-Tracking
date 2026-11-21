"""Config and options flow."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig,
    TextSelector, TextSelectorConfig, TextSelectorType,
)

from .const import CONF_PLAYERS, CONF_TMDB_KEY, CONF_WEEK_START, DEFAULT_WEEK_START, DOMAIN
from .tmdb import TmdbClient

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PLAYERS, default=defaults.get(CONF_PLAYERS, [])): EntitySelector(
            EntitySelectorConfig(domain="media_player", multiple=True)),
        vol.Optional(CONF_TMDB_KEY, description={"suggested_value": defaults.get(CONF_TMDB_KEY, "")}):
            TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_WEEK_START, default=str(defaults.get(CONF_WEEK_START, DEFAULT_WEEK_START))):
            SelectSelector(SelectSelectorConfig(
                options=[{"value": str(i), "label": d.title()} for i, d in enumerate(DAYS)], translation_key="week_start")),
    })


async def _validate(hass, user_input: dict[str, Any]) -> dict[str, str]:
    key = user_input.get(CONF_TMDB_KEY)
    if key and not await TmdbClient(async_get_clientsession(hass), key).validate():
        return {CONF_TMDB_KEY: "invalid_tmdb_key"}
    return {}


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    data = {**user_input, CONF_WEEK_START: int(user_input[CONF_WEEK_START])}
    if not data.get(CONF_TMDB_KEY):
        data.pop(CONF_TMDB_KEY, None)
    return data


class KidsScreentimeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="Kids Screentime", data=_clean(user_input))
        defaults = user_input or {CONF_PLAYERS: [
            s.entity_id for s in self.hass.states.async_all("media_player") if "apple_tv" in s.entity_id]}
        return self.async_show_form(step_id="user", data_schema=_schema(defaults), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlowWithReload:
        return KidsScreentimeOptionsFlow()


class KidsScreentimeOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(data=_clean(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(user_input or current), errors=errors)
