"""Storage manager for Local Wine Cellar."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DATA_BOTTLES,
    DATA_HISTORY,
    DATA_LOCATIONS,
    DATA_MEDIA,
    DATA_SETTINGS,
    REMOVAL_REASONS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .models import (
    blank_data,
    compute_stats,
    export_csv,
    import_csv,
    normalize_data,
    sanitize_bottle,
    sanitize_history_entry,
    sanitize_location,
    utcnow,
)


class WineCellarStorage:
    """Manage local wine cellar data."""

    # pylint: disable=too-many-public-methods

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize storage."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = blank_data()

    @property
    def bottles(self) -> list[dict[str, Any]]:
        """Return all current bottles."""
        return cast(list[dict[str, Any]], self._data[DATA_BOTTLES])

    @property
    def locations(self) -> list[dict[str, Any]]:
        """Return all locations."""
        return cast(list[dict[str, Any]], self._data[DATA_LOCATIONS])

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return removal history."""
        return cast(list[dict[str, Any]], self._data[DATA_HISTORY])

    @property
    def settings(self) -> dict[str, Any]:
        """Return settings."""
        return cast(dict[str, Any], self._data[DATA_SETTINGS])

    @property
    def media(self) -> dict[str, Any]:
        """Return media metadata."""
        return cast(dict[str, Any], self._data[DATA_MEDIA])

    async def async_load(self) -> None:
        """Load data from Home Assistant storage."""
        self._data = normalize_data(await self._store.async_load())
        await self.async_save()

    async def async_save(self) -> None:
        """Persist data to Home Assistant storage."""
        await self._store.async_save(self._data)

    def get_bottle(self, bottle_id: str) -> dict[str, Any] | None:
        """Return a bottle by id."""
        return _find_by_id(self.bottles, bottle_id)

    def get_location(self, location_id: str) -> dict[str, Any] | None:
        """Return a location by id."""
        return _find_by_id(self.locations, location_id)

    def get_history_entry(self, history_id: str) -> dict[str, Any] | None:
        """Return a history entry by id."""
        return _find_by_id(self.history, history_id)

    def add_bottle(self, bottle_data: dict[str, Any]) -> dict[str, Any]:
        """Add a bottle."""
        bottle = sanitize_bottle(
            bottle_data,
            bottle_id=str(uuid.uuid4()),
            known_location_ids=self._location_ids(),
        )
        self.bottles.append(bottle)
        return bottle

    def update_bottle(
        self, bottle_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a bottle."""
        bottle = self.get_bottle(bottle_id)
        if bottle is None:
            return None
        updated = sanitize_bottle(
            updates,
            bottle_id=bottle_id,
            known_location_ids=self._location_ids(),
            existing=bottle,
        )
        bottle.clear()
        bottle.update(updated)
        return bottle

    def move_bottle(self, bottle_id: str, location_id: str) -> dict[str, Any] | None:
        """Move a bottle to a location or unassigned."""
        return self.update_bottle(bottle_id, {"location_id": location_id})

    def duplicate_bottle(self, bottle_id: str) -> dict[str, Any] | None:
        """Duplicate a bottle as a new physical bottle."""
        bottle = self.get_bottle(bottle_id)
        if bottle is None:
            return None
        data = deepcopy(bottle)
        data.pop("id", None)
        data.pop("created_at", None)
        data.pop("updated_at", None)
        return self.add_bottle(data)

    def remove_bottle(
        self,
        bottle_id: str,
        *,
        reason: str = "other",
        notes: str = "",
    ) -> dict[str, Any] | None:
        """Remove a bottle and archive it to history."""
        bottle = self.get_bottle(bottle_id)
        if bottle is None:
            return None
        self.bottles.remove(bottle)
        entry = sanitize_history_entry(
            {
                "id": str(uuid.uuid4()),
                "bottle": deepcopy(bottle),
                "reason": reason if reason in REMOVAL_REASONS else "other",
                "notes": notes,
                "removed_at": utcnow(),
            }
        )
        self.history.insert(0, entry)
        return entry

    def restore_history_entry(self, history_id: str) -> dict[str, Any] | None:
        """Restore a removed bottle from history."""
        entry = self.get_history_entry(history_id)
        if entry is None:
            return None
        bottle_data = deepcopy(entry.get("bottle", {}))
        bottle_id = bottle_data.get("id")
        if not bottle_id or self.get_bottle(bottle_id) is not None:
            bottle_id = str(uuid.uuid4())
        bottle = sanitize_bottle(
            bottle_data,
            bottle_id=bottle_id,
            known_location_ids=self._location_ids(),
        )
        self.bottles.append(bottle)
        self.history.remove(entry)
        return bottle

    def add_location(self, location_data: dict[str, Any]) -> dict[str, Any]:
        """Add a location."""
        location = sanitize_location(location_data, location_id=str(uuid.uuid4()))
        self.locations.append(location)
        return location

    def update_location(
        self, location_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a location."""
        location = self.get_location(location_id)
        if location is None:
            return None
        updated = sanitize_location(updates, location_id=location_id, existing=location)
        location.clear()
        location.update(updated)
        return location

    def remove_location(self, location_id: str) -> bool:
        """Remove a location and unassign its bottles."""
        location = self.get_location(location_id)
        if location is None:
            return False
        self.locations.remove(location)
        for bottle in self.bottles:
            if bottle.get("location_id") == location_id:
                bottle["location_id"] = ""
                bottle["updated_at"] = utcnow()
        return True

    def set_bottle_image(self, bottle_id: str, image_id: str) -> dict[str, Any] | None:
        """Set a bottle's image id."""
        return self.update_bottle(bottle_id, {"image_id": image_id})

    def delete_bottle_image(self, bottle_id: str) -> tuple[dict[str, Any] | None, str]:
        """Remove image from a bottle and return the old image id."""
        bottle = self.get_bottle(bottle_id)
        if bottle is None:
            return None, ""
        old_image_id = bottle.get("image_id", "")
        return self.update_bottle(bottle_id, {"image_id": ""}), old_image_id

    def upsert_media(self, media_id: str, metadata: dict[str, Any]) -> None:
        """Save media metadata."""
        self.media[media_id] = metadata

    def delete_media(self, media_id: str) -> None:
        """Delete media metadata."""
        self.media.pop(media_id, None)

    def get_stats(self) -> dict[str, Any]:
        """Return inventory stats."""
        return compute_stats(self.bottles, self.locations)

    def get_backup_data(self) -> dict[str, Any]:
        """Return metadata backup data."""
        return deepcopy(self._data)

    def restore_data(self, data: dict[str, Any]) -> dict[str, int]:
        """Replace storage from backup metadata."""
        self._data = normalize_data(data)
        return {
            "bottles": len(self.bottles),
            "locations": len(self.locations),
            "history": len(self.history),
            "media": len(self.media),
        }

    def export_csv(self) -> str:
        """Export bottle metadata as CSV."""
        return export_csv(self.bottles, self.locations)

    def import_csv(self, csv_text: str) -> int:
        """Import bottle metadata from CSV."""
        rows = import_csv(csv_text, self.locations)
        for row in rows:
            self.add_bottle(row)
        return len(rows)

    def _location_ids(self) -> set[str]:
        """Return known location ids."""
        return {location["id"] for location in self.locations}


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    """Find a dict by id."""
    for item in items:
        if item.get("id") == item_id:
            return item
    return None
