from pathlib import Path

from homeassistant.helpers.service import _SERVICES_SCHEMA
from homeassistant.util.yaml import load_yaml_dict

from custom_components.kids_screentime.const import DOMAIN

SERVICES = Path(__file__).parent.parent / "custom_components" / DOMAIN / "services.yaml"


def test_services_yaml_passes_home_assistants_schema():
    _SERVICES_SCHEMA(load_yaml_dict(str(SERVICES)))


async def test_every_registered_service_is_described(hass):
    from custom_components.kids_screentime import websocket_api

    websocket_api.async_register_services(hass)
    described = set(load_yaml_dict(str(SERVICES)))
    assert set(hass.services.async_services_for_domain(DOMAIN)) == described
