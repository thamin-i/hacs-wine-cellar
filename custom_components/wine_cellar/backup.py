"""Backup helpers for Local Wine Cellar."""
# pylint: disable=duplicate-code

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .const import BACKUP_DIR, DATA_MEDIA
from .media import WineCellarMediaManager
from .storage import WineCellarStorage


async def async_create_backup_payload(
    storage: WineCellarStorage,
    media_manager: WineCellarMediaManager,
) -> dict[str, Any]:
    """Create a full backup payload including photos."""
    payload = storage.get_backup_data()
    payload["version"] = 1
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    payload["media_files"] = await media_manager.async_export_media(storage.media)
    return payload


async def async_restore_backup_payload(
    storage: WineCellarStorage,
    media_manager: WineCellarMediaManager,
    payload: dict[str, Any],
) -> dict[str, int]:
    """Restore a full backup payload."""
    if not isinstance(payload, dict):
        raise ValueError("Backup must be an object")
    restored_media = await media_manager.async_restore_media(
        payload.get("media_files", {})
    )
    data = dict(payload)
    data[DATA_MEDIA] = restored_media
    return storage.restore_data(data)


async def async_save_server_backup(
    hass: HomeAssistant,
    storage: WineCellarStorage,
    media_manager: WineCellarMediaManager,
) -> dict[str, Any]:
    """Save a full backup to the Home Assistant config directory."""
    payload = await async_create_backup_payload(storage, media_manager)
    backup_dir = await _async_backup_dir(hass)
    now = datetime.now(timezone.utc)
    filename = f"wine_cellar_{now.strftime('%Y%m%d_%H%M%S')}.json"
    path = backup_dir / filename
    await hass.async_add_executor_job(
        path.write_text, json.dumps(payload, indent=2), "utf-8"
    )
    return {
        "filename": filename,
        "bottles": len(storage.bottles),
        "locations": len(storage.locations),
        "history": len(storage.history),
        "media": len(storage.media),
        "created_at": payload["created_at"],
    }


async def async_list_server_backups(hass: HomeAssistant) -> list[dict[str, Any]]:
    """List available server backups."""
    backup_dir = await _async_backup_dir(hass)

    def _list() -> list[dict[str, Any]]:
        result = []
        for path in sorted(backup_dir.glob("wine_cellar_*.json"), reverse=True)[:20]:
            try:
                payload = json.loads(path.read_text("utf-8"))
                result.append(
                    {
                        "filename": path.name,
                        "created_at": payload.get("created_at", ""),
                        "bottles": len(payload.get("bottles", [])),
                        "locations": len(payload.get("locations", [])),
                        "history": len(payload.get("history", [])),
                        "media": len(payload.get("media_files", {})),
                        "size": path.stat().st_size,
                    }
                )
            except (OSError, json.JSONDecodeError):
                result.append({"filename": path.name, "error": "unreadable"})
        return result

    return cast(list[dict[str, Any]], await hass.async_add_executor_job(_list))


async def async_restore_server_backup(
    hass: HomeAssistant,
    storage: WineCellarStorage,
    media_manager: WineCellarMediaManager,
    filename: str,
) -> dict[str, int]:
    """Restore a server backup by filename."""
    backup_dir = await _async_backup_dir(hass)
    path = backup_dir / filename
    if not _is_child(path, backup_dir) or path.name != filename:
        raise ValueError("Invalid backup filename")
    if not path.exists():
        raise ValueError("Backup file not found")
    text = await hass.async_add_executor_job(path.read_text, "utf-8")
    payload = json.loads(text)
    return await async_restore_backup_payload(storage, media_manager, payload)


async def _async_backup_dir(hass: HomeAssistant) -> Path:
    """Return backup directory."""
    path = Path(hass.config.config_dir) / BACKUP_DIR
    await hass.async_add_executor_job(_ensure_dir, path)
    return path


def _ensure_dir(path: Path) -> None:
    """Create a directory if it does not already exist."""
    path.mkdir(exist_ok=True)


def _is_child(path: Path, parent: Path) -> bool:
    """Return true if path resolves inside parent."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True
