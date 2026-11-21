from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kids_screentime import websocket_api as api
from custom_components.kids_screentime.const import DOMAIN
from custom_components.kids_screentime.models import Segment, Show, Verdict
from custom_components.kids_screentime.resolver import ShowResolver
from custom_components.kids_screentime.runtime import RuntimeData
from custom_components.kids_screentime.store import ScreentimeStore
from custom_components.kids_screentime.tracker import SessionTracker

T0 = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


def seg(seg_id, start, key="bluey", minutes=10):
    return Segment(
        id=seg_id, device="media_player.tv", app_id=None, app_name="Disney+", title=key, series=key,
        season=None, episode=None, media_type="tvshow", show_key=key, start=start,
        end=start + timedelta(minutes=minutes), seconds=minutes * 60, position_max=None, duration_total=None,
    )


@pytest.fixture
async def store(hass):
    s = ScreentimeStore(hass)
    await s.async_load()
    for key, verdict in (("bluey", Verdict.COUNT), ("mystery", Verdict.REVIEW)):
        s.upsert_show(Show(key, key.title(), "TV-Y", 1, True, verdict, "auto", False, T0, T0))
    s.add_segment(seg("a", T0))
    s.add_segment(seg("b", T0 + timedelta(hours=1)))
    s.add_segment(seg("c", T0 + timedelta(hours=2), key="mystery"))
    resolver = ShowResolver(s, None)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entry.runtime_data = RuntimeData(s, resolver, SessionTracker(hass, s, resolver, []), ZoneInfo("UTC"), 6)
    api.async_register(hass)
    api.async_register_services(hass)
    return s


@pytest.fixture
async def ws(hass, hass_ws_client, store):
    return await hass_ws_client(hass)


async def call(ws, type_, **kw):
    ws.next_id = getattr(ws, "next_id", 0) + 1
    await ws.send_json({"id": ws.next_id, "type": f"kids_screentime/{type_}", **kw})
    return await ws.receive_json()


async def test_summary_command_returns_shape(ws):
    msg = await call(ws, "summary", days=14, weeks=12)
    assert msg["success"]
    r = msg["result"]
    assert {"today_minutes", "pending_minutes", "week_start", "days", "weeks", "apps", "shows"} <= set(r)
    assert len(r["days"]) == 14 and len(r["weeks"]) == 12


async def test_non_admin_is_refused(hass, hass_ws_client, hass_read_only_access_token, store):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    msg = await call(client, "summary", days=7, weeks=4)
    assert not msg["success"] and msg["error"]["code"] == "unauthorized"


async def test_sessions_paged_newest_first(ws):
    first = (await call(ws, "sessions", limit=2))["result"]
    assert [s["id"] for s in first] == ["c", "b"]
    assert first[0]["pending"] is True and first[1]["pending"] is False
    assert first[1]["show_title"] == "Bluey" and first[1]["minutes"] == 10
    rest = (await call(ws, "sessions", limit=2, before=first[-1]["start"]))["result"]
    assert [s["id"] for s in rest] == ["a"]


async def test_delete_session_persists(ws, store):
    assert (await call(ws, "delete_session", session_id="a"))["success"]
    assert "a" not in store.segments


async def test_delete_show_blocks_and_removes(ws, store):
    assert (await call(ws, "delete_show", key="bluey"))["success"]
    assert not any(s.show_key == "bluey" for s in store.segments.values())
    shows = {s["key"]: s for s in (await call(ws, "shows"))["result"]}
    assert shows["bluey"]["blocked"] is True


async def test_undo_block_via_set_rule_none(ws):
    await call(ws, "delete_show", key="bluey")
    assert (await call(ws, "set_rule", key="bluey", rule=None))["success"]
    shows = {s["key"]: s for s in (await call(ws, "shows"))["result"]}
    assert shows["bluey"]["blocked"] is False


async def test_review_lists_and_resolves(ws, store):
    review = (await call(ws, "review"))["result"]
    assert [r["key"] for r in review] == ["mystery"] and review[0]["minutes"] == 10
    assert (await call(ws, "resolve_review", key="mystery", count=True))["success"]
    assert store.shows["mystery"].verdict == Verdict.COUNT


async def test_unknown_id_returns_not_found_error(ws):
    msg = await call(ws, "delete_session", session_id="nope")
    assert not msg["success"] and msg["error"]["code"] == "not_found"


async def test_delete_session_service(hass, store):
    await hass.services.async_call(DOMAIN, "delete_session", {"session_id": "b"}, blocking=True)
    assert "b" not in store.segments


async def test_set_show_rule_service(hass, store):
    await hass.services.async_call(DOMAIN, "set_show_rule", {"key": "bluey", "rule": "never"}, blocking=True)
    assert "bluey" in store.rules.never


async def test_add_list_and_delete_a_quiet_window(ws, store):
    added = await call(ws, "add_quiet_window", apps=["Netflix"], days=[2], start="21:00", end="23:00", label="Wed night")
    assert added["success"]
    window_id = added["result"]["id"]
    listed = (await call(ws, "quiet_windows"))["result"]
    assert listed == [{"id": window_id, "apps": ["Netflix"], "days": [2], "start": "21:00", "end": "23:00", "label": "Wed night"}]
    assert (await call(ws, "delete_quiet_window", window_id=window_id))["success"]
    assert (await call(ws, "quiet_windows"))["result"] == []
    assert (await call(ws, "delete_quiet_window", window_id=window_id))["error"]["code"] == "not_found"


async def test_a_bad_quiet_window_is_refused(ws):
    msg = await call(ws, "add_quiet_window", apps=[], days=[], start="21:00", end="23:00")
    assert not msg["success"] and msg["error"]["code"] == "invalid_format"


async def test_sessions_show_how_much_counted_after_filters(ws, store):
    from custom_components.kids_screentime.models import QuietWindow

    store.rules.quiet_windows.append(QuietWindow("w", [], list(range(7)), "10:00", "10:05"))  # every day, 10:00-10:05
    rows = (await call(ws, "sessions", limit=10))["result"]
    a = next(r for r in rows if r["id"] == "a")  # 10:00-10:10 -> 5 of 10 minutes count
    assert (a["minutes"], a["counted_minutes"]) == (10, 5)
    b = next(r for r in rows if r["id"] == "b")  # 11:00, unaffected
    assert b["counted_minutes"] == b["minutes"]
