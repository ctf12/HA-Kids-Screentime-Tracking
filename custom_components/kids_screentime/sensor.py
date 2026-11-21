"""Today, this-week and pending-review sensors."""
from __future__ import annotations

from datetime import tzinfo
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIGNAL_UPDATED
from .store import ScreentimeStore
from .summary import breakdown, build_summary, pending_minutes, week_start_date


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _key = ""

    def __init__(self, store: ScreentimeStore, entry_id: str) -> None:
        self._store = store
        self._attr_unique_id = f"{entry_id}_{self._key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name="Kids Screentime")

    async def async_added_to_hass(self) -> None:
        @callback
        def _refresh() -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, _refresh))
        # Today and this week roll over at local midnight even if nothing plays.
        @callback
        def _midnight(_now) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(self.hass, _midnight, hour=0, minute=0, second=5))


class _Windowed(_Base):
    def __init__(self, store: ScreentimeStore, entry_id: str, tz: tzinfo, week_start: int) -> None:
        super().__init__(store, entry_id)
        self._tz = tz
        self._week_start = week_start

    def _today(self):
        return dt_util.utcnow().astimezone(self._tz).date()

    def _first_day(self):
        raise NotImplementedError

    @property
    def native_value(self) -> int:
        now = dt_util.utcnow()
        summary = build_summary(self._store, self._tz, now, 14, 1, self._week_start)
        return self._minutes(summary)

    def _minutes(self, summary: dict[str, Any]) -> int:
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        apps, shows = breakdown(self._store, self._tz, self._first_day(), self._today())
        return {"by_app": apps, "by_show": shows}


class TodaySensor(_Windowed):
    _key = "today"
    _attr_name = "Today"

    def _first_day(self):
        return self._today()

    def _minutes(self, summary: dict[str, Any]) -> int:
        return summary["today_minutes"]


class WeekSensor(_Windowed):
    _key = "week"
    _attr_name = "This week"

    def _first_day(self):
        return week_start_date(self._today(), self._week_start)

    def _minutes(self, summary: dict[str, Any]) -> int:
        return summary["weeks"][-1]["minutes"]


class PendingSensor(_Base):
    _key = "pending_review"
    _attr_name = "Pending review"

    def __init__(self, store: ScreentimeStore, entry_id: str, tz: tzinfo | None = None) -> None:
        super().__init__(store, entry_id)
        self._tz = tz

    @property
    def native_value(self) -> int:
        return pending_minutes(self._store, self._tz) if self._tz else pending_minutes(self._store)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities([
        TodaySensor(data.store, entry.entry_id, data.tz, data.week_start),
        WeekSensor(data.store, entry.entry_id, data.tz, data.week_start),
        PendingSensor(data.store, entry.entry_id, data.tz),
    ])
