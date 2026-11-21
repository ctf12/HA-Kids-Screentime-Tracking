"""Websocket commands and services for the panel and the HaCasa2 dashboard."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api as ha_ws
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_UPDATED
from .models import Verdict
from .runtime import RuntimeData
from .summary import build_summary

RULE = vol.Any(None, "always", "never")


def _runtime(hass: HomeAssistant) -> RuntimeData:
    for entry in hass.config_entries.async_entries(DOMAIN):
        data = getattr(entry, "runtime_data", None)
        if data is not None:
            return data
    raise HomeAssistantError("Kids Screentime is not set up")


def _changed(hass: HomeAssistant) -> None:
    async_dispatcher_send(hass, SIGNAL_UPDATED)


def _show_rows(data: RuntimeData) -> list[dict[str, Any]]:
    store = data.store
    seconds: dict[str, float] = {}
    percent: dict[str, int | None] = {}
    for seg in store.segments.values():
        seconds[seg.show_key] = seconds.get(seg.show_key, 0.0) + seg.seconds
        if seg.position_max is not None and seg.duration_total:
            pct = round(100 * min(1.0, seg.position_max / seg.duration_total))
            percent[seg.show_key] = max(percent.get(seg.show_key) or 0, pct)
    rows = []
    keys = list(store.shows) + [k for k in sorted(store.rules.never) if k not in store.shows]
    for key in keys:
        show = store.shows.get(key)
        blocked = key in store.rules.never
        if show is not None and show.verdict == Verdict.DISCARD and not blocked:
            continue
        rows.append({
            "key": key,
            "title": show.title if show else key,
            "rating": show.rating if show else None,
            "source": show.source if show else "manual",
            "verdict": (show.verdict.value if show else Verdict.DISCARD.value),
            "minutes": round(seconds.get(key, 0.0) / 60),
            "percent": percent.get(key),
            "blocked": blocked,
        })
    rows.sort(key=lambda r: -r["minutes"])
    return rows


@ha_ws.websocket_command({
    vol.Required("type"): "kids_screentime/summary",
    vol.Required("days"): vol.All(int, vol.Range(min=1, max=90)),
    vol.Required("weeks"): vol.All(int, vol.Range(min=1, max=52)),
})
@ha_ws.require_admin
@callback
def ws_summary(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    data = _runtime(hass)
    connection.send_result(msg["id"], build_summary(
        data.store, data.tz, dt_util.utcnow(), msg["days"], msg["weeks"], data.week_start))


@ha_ws.websocket_command({
    vol.Required("type"): "kids_screentime/sessions",
    vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=500)),
    vol.Optional("before"): vol.Any(None, str),
})
@ha_ws.require_admin
@callback
def ws_sessions(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    store = _runtime(hass).store
    segments = sorted(store.segments.values(), key=lambda s: s.start, reverse=True)
    if msg.get("before"):
        cutoff = dt_util.parse_datetime(msg["before"])
        if cutoff is None:
            connection.send_error(msg["id"], "invalid_format", "before must be an ISO datetime")
            return
        segments = [s for s in segments if s.start < cutoff]
    rows = []
    for seg in segments[: msg["limit"]]:
        show = store.shows.get(seg.show_key)
        rows.append({
            "id": seg.id, "show_key": seg.show_key,
            "show_title": show.title if show else seg.title,
            "app": seg.app_name, "device": seg.device,
            "start": seg.start.isoformat(), "end": seg.end.isoformat(),
            "minutes": round(seg.seconds / 60),
            "pending": store.segment_verdict(seg) == Verdict.REVIEW,
        })
    connection.send_result(msg["id"], rows)


@ha_ws.websocket_command({vol.Required("type"): "kids_screentime/shows"})
@ha_ws.require_admin
@callback
def ws_shows(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], _show_rows(_runtime(hass)))


@ha_ws.websocket_command({vol.Required("type"): "kids_screentime/review"})
@ha_ws.require_admin
@callback
def ws_review(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    rows = [r for r in _show_rows(_runtime(hass)) if r["verdict"] == Verdict.REVIEW.value]
    connection.send_result(msg["id"], rows)


@ha_ws.websocket_command({vol.Required("type"): "kids_screentime/delete_session", vol.Required("session_id"): str})
@ha_ws.require_admin
@callback
def ws_delete_session(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    if not _runtime(hass).store.delete_segment(msg["session_id"]):
        connection.send_error(msg["id"], "not_found", "No such session")
        return
    _changed(hass)
    connection.send_result(msg["id"])


@ha_ws.websocket_command({vol.Required("type"): "kids_screentime/delete_show", vol.Required("key"): str})
@ha_ws.require_admin
@callback
def ws_delete_show(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    removed = _runtime(hass).store.delete_show(msg["key"])
    _changed(hass)
    connection.send_result(msg["id"], {"removed": removed})


@ha_ws.websocket_command({
    vol.Required("type"): "kids_screentime/set_rule", vol.Required("key"): str, vol.Required("rule"): RULE,
})
@ha_ws.require_admin
@callback
def ws_set_rule(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    _runtime(hass).store.set_rule(msg["key"], msg["rule"])
    _changed(hass)
    connection.send_result(msg["id"])


@ha_ws.websocket_command({
    vol.Required("type"): "kids_screentime/resolve_review", vol.Required("key"): str, vol.Required("count"): bool,
})
@ha_ws.require_admin
@callback
def ws_resolve_review(hass: HomeAssistant, connection: ha_ws.ActiveConnection, msg: dict[str, Any]) -> None:
    _runtime(hass).store.resolve_review(msg["key"], msg["count"])
    _changed(hass)
    connection.send_result(msg["id"])


def async_register(hass: HomeAssistant) -> None:
    for handler in (
        ws_summary, ws_sessions, ws_shows, ws_review, ws_delete_session,
        ws_delete_show, ws_set_rule, ws_resolve_review,
    ):
        ha_ws.async_register_command(hass, handler)


def async_register_services(hass: HomeAssistant) -> None:
    async def delete_session(call: ServiceCall) -> None:
        if not _runtime(hass).store.delete_segment(call.data["session_id"]):
            raise ServiceValidationError("No such session")
        _changed(hass)

    async def delete_show(call: ServiceCall) -> None:
        _runtime(hass).store.delete_show(call.data["key"])
        _changed(hass)

    async def set_show_rule(call: ServiceCall) -> None:
        _runtime(hass).store.set_rule(call.data["key"], call.data["rule"])
        _changed(hass)

    async def resolve_review(call: ServiceCall) -> None:
        _runtime(hass).store.resolve_review(call.data["key"], call.data["count"])
        _changed(hass)

    for name, handler, schema in (
        ("delete_session", delete_session, {vol.Required("session_id"): str}),
        ("delete_show", delete_show, {vol.Required("key"): str}),
        ("set_show_rule", set_show_rule, {vol.Required("key"): str, vol.Optional("rule", default=None): RULE}),
        ("resolve_review", resolve_review, {vol.Required("key"): str, vol.Required("count"): bool}),
    ):
        async_register_admin_service(hass, DOMAIN, name, handler, schema=vol.Schema(schema))
