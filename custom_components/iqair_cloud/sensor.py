from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_SERIAL_NUMBER, DOMAIN
from .coordinator import IQAirDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# path, name, unit, device_class
SENSORS: tuple[tuple[str, str, str | None, SensorDeviceClass | None], ...] = (
    ("current.pm25.value", "PM2.5", "µg/m³", SensorDeviceClass.PM25),
    ("current.pc.value", "Particle count", "/L", None),
    ("current.aqi.value", "AQI", None, None),
    ("current.pm25.aqi", "PM2.5 AQI", None, None),
    ("current.ts", "Last reading", None, SensorDeviceClass.TIMESTAMP),
    ("remote.filters[0].healthPercent", "HEPA pre-filter health", PERCENTAGE, None),
    ("remote.filters[1].healthPercent", "Gas & odour filter health", PERCENTAGE, None),
    ("connectivity.percentage", "Wi-Fi signal", PERCENTAGE, None),
    ("performance.cleanAirDeliveryRatePercent", "CADR utilisation", PERCENTAGE, None),
)


def _get_path(data: Any, path: str) -> Any:
    """Resolve 'a.b[0].c' against a nested dict/list payload."""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        key, _, idx = part.partition("[")
        cur = cur.get(key)
        if idx:
            try:
                cur = cur[int(idx.rstrip("]"))]
            except (IndexError, TypeError, ValueError):
                return None
        if cur is None:
            return None
    return cur


def _device_info(entry: ConfigEntry, data: dict[str, Any]) -> DeviceInfo:
    """Shared device registry entry so all entities group under one purifier."""
    return DeviceInfo(
        identifiers={(DOMAIN, str(entry.data.get(CONF_SERIAL_NUMBER) or entry.entry_id))},
        manufacturer="IQAir",
        model=data.get("modelLabel") or data.get("model"),
        name=data.get("name") or "IQAir purifier",
        serial_number=entry.data.get(CONF_SERIAL_NUMBER),
    )


class IQAirSensor(CoordinatorEntity[IQAirDataUpdateCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IQAirDataUpdateCoordinator,
        entry: ConfigEntry,
        path: str,
        name: str,
        unit: str | None,
        dclass: SensorDeviceClass | None,
    ) -> None:
        super().__init__(coordinator)
        self._path = path
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dclass
        self._attr_device_info = _device_info(entry, coordinator.data or {})
        if dclass is not SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{entry.entry_id}_{path}"

    @property
    def native_value(self) -> Any:
        raw = _get_path(self.coordinator.data or {}, self._path)
        if self.device_class is SensorDeviceClass.TIMESTAMP:
            return dt_util.parse_datetime(raw) if isinstance(raw, str) else raw
        return raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: IQAirDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        IQAirSensor(coordinator, entry, path, name, unit, dclass)
        for path, name, unit, dclass in SENSORS
        if _get_path(coordinator.data or {}, path) is not None
    ]
    if not entities:
        _LOGGER.warning("IQAir: no configured reading paths present in the payload")
    async_add_entities(entities)
