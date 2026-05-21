"""Pure data helpers for Local Wine Cellar."""

from __future__ import annotations

import csv
import io
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .const import (
    DATA_BOTTLES,
    DATA_HISTORY,
    DATA_LOCATIONS,
    DATA_MEDIA,
    DATA_SETTINGS,
    DEFAULT_SETTINGS,
    LOCATION_TYPES,
    REMOVAL_REASONS,
    WINE_TYPES,
)

REMOTE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

BOTTLE_FIELDS = (
    "id",
    "name",
    "producer",
    "vintage",
    "wine_type",
    "country",
    "region",
    "appellation",
    "grapes",
    "bottle_size",
    "purchase_price",
    "estimated_value",
    "purchase_date",
    "drink_from",
    "drink_by",
    "rating",
    "notes",
    "tags",
    "barcode",
    "location_id",
    "image_id",
    "created_at",
    "updated_at",
)

CSV_FIELDS = (
    "name",
    "producer",
    "vintage",
    "wine_type",
    "country",
    "region",
    "appellation",
    "grapes",
    "bottle_size",
    "purchase_price",
    "estimated_value",
    "purchase_date",
    "drink_from",
    "drink_by",
    "rating",
    "notes",
    "tags",
    "barcode",
    "location_name",
)


def utcnow() -> str:
    """Return an ISO formatted UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def blank_data() -> dict[str, Any]:
    """Return a new empty storage payload."""
    return {
        DATA_BOTTLES: [],
        DATA_LOCATIONS: [],
        DATA_HISTORY: [],
        DATA_SETTINGS: dict(DEFAULT_SETTINGS),
        DATA_MEDIA: {},
    }


def normalize_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a stored payload into the current schema."""
    if not isinstance(data, dict):
        return blank_data()

    normalized = blank_data()
    normalized[DATA_SETTINGS].update(
        data.get(DATA_SETTINGS, {}) if isinstance(data.get(DATA_SETTINGS), dict) else {}
    )
    normalized[DATA_MEDIA] = (
        data.get(DATA_MEDIA, {}) if isinstance(data.get(DATA_MEDIA), dict) else {}
    )

    normalized[DATA_LOCATIONS] = [
        sanitize_location(location)
        for location in data.get(DATA_LOCATIONS, [])
        if isinstance(location, dict)
    ]
    location_ids = {location["id"] for location in normalized[DATA_LOCATIONS]}

    normalized[DATA_BOTTLES] = [
        sanitize_bottle(bottle, known_location_ids=location_ids)
        for bottle in data.get(DATA_BOTTLES, [])
        if isinstance(bottle, dict)
    ]

    normalized[DATA_HISTORY] = [
        sanitize_history_entry(entry)
        for entry in data.get(DATA_HISTORY, [])
        if isinstance(entry, dict)
    ]
    return normalized


def sanitize_bottle(
    source: dict[str, Any],
    *,
    bottle_id: str | None = None,
    known_location_ids: set[str] | None = None,
    existing: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return a safe bottle record."""
    timestamp = now or utcnow()
    base = dict(existing or {})
    record = {
        "id": bottle_id or _clean_str(base.get("id") or source.get("id")),
        "name": _clean_str(source.get("name", base.get("name", "")))
        or "Unnamed bottle",
        "producer": _clean_str(source.get("producer", base.get("producer", ""))),
        "vintage": _clean_year(source.get("vintage", base.get("vintage"))),
        "wine_type": _enum(
            _clean_str(
                source.get(
                    "wine_type", source.get("type", base.get("wine_type", "red"))
                )
            ),
            WINE_TYPES,
            "red",
        ),
        "country": _clean_str(source.get("country", base.get("country", ""))),
        "region": _clean_str(source.get("region", base.get("region", ""))),
        "appellation": _clean_str(
            source.get("appellation", base.get("appellation", ""))
        ),
        "grapes": _clean_str(source.get("grapes", base.get("grapes", ""))),
        "bottle_size": _clean_str(
            source.get("bottle_size", base.get("bottle_size", "750ml"))
        )
        or "750ml",
        "purchase_price": _clean_float(
            source.get("purchase_price", base.get("purchase_price"))
        ),
        "estimated_value": _clean_float(
            source.get("estimated_value", base.get("estimated_value"))
        ),
        "purchase_date": _clean_str(
            source.get("purchase_date", base.get("purchase_date", ""))
        ),
        "drink_from": _clean_year(source.get("drink_from", base.get("drink_from"))),
        "drink_by": _clean_year(source.get("drink_by", base.get("drink_by"))),
        "rating": _clean_rating(source.get("rating", base.get("rating"))),
        "notes": _clean_str(source.get("notes", base.get("notes", "")), limit=4000),
        "tags": _clean_tags(source.get("tags", base.get("tags", []))),
        "barcode": _clean_str(source.get("barcode", base.get("barcode", ""))),
        "location_id": _clean_str(
            source.get("location_id", base.get("location_id", ""))
        ),
        "image_id": _clean_local_image_id(
            source.get("image_id", base.get("image_id", ""))
        ),
        "created_at": _clean_str(base.get("created_at") or source.get("created_at"))
        or timestamp,
        "updated_at": timestamp,
    }

    if (
        known_location_ids is not None
        and record["location_id"] not in known_location_ids
    ):
        record["location_id"] = ""

    if not record["id"]:
        raise ValueError("Bottle id is required")

    return record


def sanitize_location(
    source: dict[str, Any],
    *,
    location_id: str | None = None,
    existing: dict[str, Any] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return a safe location record."""
    timestamp = now or utcnow()
    base = dict(existing or {})
    record = {
        "id": location_id or _clean_str(base.get("id") or source.get("id")),
        "name": _clean_str(source.get("name", base.get("name", "")))
        or "Unnamed location",
        "location_type": _enum(
            _clean_str(
                source.get(
                    "location_type",
                    source.get("type", base.get("location_type", "rack")),
                )
            ),
            LOCATION_TYPES,
            "rack",
        ),
        "capacity": max(
            0, _clean_int(source.get("capacity", base.get("capacity"))) or 0
        ),
        "notes": _clean_str(source.get("notes", base.get("notes", "")), limit=1000),
        "created_at": _clean_str(base.get("created_at") or source.get("created_at"))
        or timestamp,
        "updated_at": timestamp,
    }
    if not record["id"]:
        raise ValueError("Location id is required")
    return record


def sanitize_history_entry(source: dict[str, Any]) -> dict[str, Any]:
    """Return a safe history entry."""
    bottle = source.get("bottle", {})
    if not isinstance(bottle, dict):
        bottle = {}
    return {
        "id": _clean_str(source.get("id")),
        "bottle": {field: deepcopy(bottle.get(field)) for field in BOTTLE_FIELDS},
        "reason": _enum(_clean_str(source.get("reason")), REMOVAL_REASONS, "other"),
        "notes": _clean_str(source.get("notes", ""), limit=2000),
        "removed_at": _clean_str(source.get("removed_at")) or utcnow(),
    }


def compute_stats(
    bottles: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    *,
    current_year: int | None = None,
) -> dict[str, Any]:
    """Compute inventory stats."""
    # pylint: disable=too-many-locals
    year = current_year or datetime.now().year
    total_capacity = sum(
        max(0, int(location.get("capacity") or 0)) for location in locations
    )
    location_ids = {location.get("id") for location in locations}
    by_type: dict[str, int] = {}
    by_location: dict[str, int] = {}
    ready = 0
    past_peak = 0
    unassigned = 0
    total_value = 0.0

    for bottle in bottles:
        wine_type = bottle.get("wine_type") or "other"
        by_type[wine_type] = by_type.get(wine_type, 0) + 1
        location_id = bottle.get("location_id") or ""
        if location_id and location_id in location_ids:
            by_location[location_id] = by_location.get(location_id, 0) + 1
        else:
            unassigned += 1

        value = bottle.get("estimated_value")
        if isinstance(value, (int, float)):
            total_value += float(value)

        drink_from = bottle.get("drink_from")
        drink_by = bottle.get("drink_by")
        has_drink_window = drink_from is not None or drink_by is not None
        if drink_by and isinstance(drink_by, int) and drink_by < year:
            past_peak += 1
        elif _is_ready_to_drink(drink_from, drink_by, has_drink_window, year):
            ready += 1

    used_capacity = (
        round((len(bottles) / total_capacity) * 100, 1) if total_capacity else 0
    )

    return {
        "total_bottles": len(bottles),
        "total_value": round(total_value, 2),
        "ready_to_drink": ready,
        "past_peak": past_peak,
        "total_capacity": total_capacity,
        "capacity_used": used_capacity,
        "available_slots": max(0, total_capacity - len(bottles)),
        "unassigned_bottles": unassigned,
        "by_type": by_type,
        "by_location": by_location,
    }


def export_csv(bottles: list[dict[str, Any]], locations: list[dict[str, Any]]) -> str:
    """Export bottle metadata to CSV."""
    location_names = {location["id"]: location["name"] for location in locations}
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for bottle in bottles:
        row = {field: "" for field in CSV_FIELDS}
        for field in CSV_FIELDS:
            if field == "location_name":
                row[field] = location_names.get(bottle.get("location_id"), "")
            elif field == "tags":
                row[field] = ", ".join(bottle.get("tags") or [])
            else:
                row[field] = bottle.get(field, "")
        writer.writerow(row)
    return output.getvalue()


def import_csv(csv_text: str, locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse bottle metadata from CSV text."""
    name_to_location = {
        str(location.get("name", "")).casefold(): location.get("id", "")
        for location in locations
    }
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        if not row.get("name"):
            continue
        raw = dict(row)
        if raw.get("location_name"):
            raw["location_id"] = name_to_location.get(
                raw["location_name"].casefold(), ""
            )
        rows.append(raw)
    return rows


def _is_ready_to_drink(
    drink_from: Any, drink_by: Any, has_drink_window: bool, year: int
) -> bool:
    """Return whether a bottle is inside its manually entered drinking window."""
    starts_now_or_earlier = drink_from is None or (
        isinstance(drink_from, int) and drink_from <= year
    )
    ends_now_or_later = drink_by is None or (
        isinstance(drink_by, int) and drink_by >= year
    )
    return has_drink_window and starts_now_or_earlier and ends_now_or_later


def _clean_str(value: Any, *, limit: int = 500) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit]


def _clean_local_image_id(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if REMOTE_URL_RE.match(text):
        return ""
    return text[:128]


def _clean_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_year(value: Any) -> int | None:
    year = _clean_int(value)
    if year is None or year < 1900 or year > 2200:
        return None
    return year


def _clean_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number, 2)


def _clean_rating(value: Any) -> float | None:
    rating = _clean_float(value)
    if rating is None:
        return None
    if rating < 0 or rating > 5:
        return None
    return rating


def _clean_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    tags = []
    for item in raw:
        tag = _clean_str(item, limit=50)
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


def _enum(value: str, choices: tuple[str, ...], fallback: str) -> str:
    return value if value in choices else fallback
