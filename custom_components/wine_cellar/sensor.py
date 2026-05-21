"""Sensors for Local Wine Cellar."""
# pylint: disable=too-many-arguments,too-many-positional-arguments

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_UPDATED
from .storage import WineCellarStorage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Local Wine Cellar sensors."""
    storage = cast(WineCellarStorage, hass.data[DOMAIN]["storage"])
    entities: list[SensorEntity] = [
        WineCellarMetricSensor(
            storage,
            entry,
            "total_bottles",
            "Total Bottles",
            "mdi:bottle-wine",
            "bottles",
        ),
        WineCellarMetricSensor(
            storage, entry, "total_value", "Total Value", "mdi:cash", None
        ),
        WineCellarMetricSensor(
            storage,
            entry,
            "ready_to_drink",
            "Ready To Drink",
            "mdi:glass-wine",
            "bottles",
        ),
        WineCellarMetricSensor(
            storage, entry, "past_peak", "Past Peak", "mdi:calendar-alert", "bottles"
        ),
        WineCellarMetricSensor(
            storage, entry, "capacity_used", "Capacity Used", "mdi:gauge", "%"
        ),
        WineCellarMetricSensor(
            storage,
            entry,
            "unassigned_bottles",
            "Unassigned Bottles",
            "mdi:map-marker-question",
            "bottles",
        ),
    ]
    known_location_ids: set[str] = set()

    def add_location_entities() -> None:
        new_entities = []
        for location in storage.locations:
            location_id = location["id"]
            if location_id not in known_location_ids:
                known_location_ids.add(location_id)
                entity = WineCellarLocationSensor(storage, entry, location_id)
                entities.append(entity)
                new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)

    async_add_entities(entities)
    add_location_entities()

    @callback
    def _async_on_update(_event: Any) -> None:
        """Refresh sensors after data changes."""
        add_location_entities()
        for entity in entities:
            entity.async_schedule_update_ha_state(True)

    entry.async_on_unload(hass.bus.async_listen(EVENT_UPDATED, _async_on_update))


class WineCellarMetricSensor(SensorEntity):
    """Sensor for a computed wine cellar metric."""

    def __init__(
        self,
        storage: WineCellarStorage,
        entry: ConfigEntry,
        metric: str,
        name: str,
        icon: str,
        unit: str | None,
    ) -> None:
        """Initialize sensor."""
        self._storage = storage
        self._metric = metric
        self._attr_unique_id = f"{entry.entry_id}_{metric}"
        self._attr_name = f"Wine Cellar {name}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        """Return metric value."""
        return self._storage.get_stats().get(self._metric)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return stats as attributes."""
        return self._storage.get_stats()


class WineCellarLocationSensor(SensorEntity):
    """Sensor for one location's bottle count."""

    _attr_icon = "mdi:map-marker"
    _attr_native_unit_of_measurement = "bottles"

    def __init__(
        self, storage: WineCellarStorage, entry: ConfigEntry, location_id: str
    ) -> None:
        """Initialize sensor."""
        self._storage = storage
        self._location_id = location_id
        self._attr_unique_id = f"{entry.entry_id}_location_{location_id}"

    @property
    def available(self) -> bool:
        """Return availability."""
        return self._location is not None

    @property
    def name(self) -> str:
        """Return sensor name."""
        location = self._location
        label = (
            location.get("name", "Removed Location") if location else "Removed Location"
        )
        return f"Wine Cellar {label}"

    @property
    def native_value(self) -> int | None:
        """Return bottle count."""
        if self._location is None:
            return None
        return sum(
            1
            for bottle in self._storage.bottles
            if bottle.get("location_id") == self._location_id
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return location attributes."""
        location = self._location
        if location is None:
            return {}
        count = self.native_value or 0
        capacity = location.get("capacity") or 0
        return {
            "location_id": self._location_id,
            "location_type": location.get("location_type"),
            "capacity": capacity,
            "available_slots": max(0, capacity - count),
        }

    @property
    def _location(self) -> dict[str, Any] | None:
        return self._storage.get_location(self._location_id)
