"""WebSocket API for Local Wine Cellar."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .backup import (
    async_create_backup_payload,
    async_list_server_backups,
    async_restore_backup_payload,
    async_restore_server_backup,
    async_save_server_backup,
)
from .const import DOMAIN, EVENT_UPDATED

_LOGGER = logging.getLogger(__name__)


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register websocket commands."""
    websocket_api.async_register_command(hass, ws_get_data)
    websocket_api.async_register_command(hass, ws_add_bottle)
    websocket_api.async_register_command(hass, ws_update_bottle)
    websocket_api.async_register_command(hass, ws_remove_bottle)
    websocket_api.async_register_command(hass, ws_restore_history)
    websocket_api.async_register_command(hass, ws_duplicate_bottle)
    websocket_api.async_register_command(hass, ws_move_bottle)
    websocket_api.async_register_command(hass, ws_set_bottle_photo)
    websocket_api.async_register_command(hass, ws_delete_bottle_photo)
    websocket_api.async_register_command(hass, ws_add_location)
    websocket_api.async_register_command(hass, ws_update_location)
    websocket_api.async_register_command(hass, ws_remove_location)
    websocket_api.async_register_command(hass, ws_get_backup)
    websocket_api.async_register_command(hass, ws_restore_backup)
    websocket_api.async_register_command(hass, ws_server_backup_save)
    websocket_api.async_register_command(hass, ws_server_backup_list)
    websocket_api.async_register_command(hass, ws_server_backup_restore)
    websocket_api.async_register_command(hass, ws_export_csv)
    websocket_api.async_register_command(hass, ws_import_csv)


@websocket_api.websocket_command({vol.Required("type"): "wine_cellar/get_data"})
@callback
def ws_get_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full local cellar data for the dashboard."""
    connection.send_result(msg["id"], _public_payload(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/add_bottle",
        vol.Required("bottle"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_add_bottle(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Add a bottle."""
    storage = hass.data[DOMAIN]["storage"]
    try:
        bottle = storage.add_bottle(msg["bottle"])
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})
    except ValueError as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/update_bottle",
        vol.Required("bottle_id"): str,
        vol.Required("updates"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update_bottle(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update a bottle."""
    storage = hass.data[DOMAIN]["storage"]
    try:
        bottle = storage.update_bottle(msg["bottle_id"], msg["updates"])
        if bottle is None:
            connection.send_result(msg["id"], {"error": "Bottle not found"})
            return
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})
    except ValueError as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/remove_bottle",
        vol.Required("bottle_id"): str,
        vol.Optional("reason", default="other"): str,
        vol.Optional("notes", default=""): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_remove_bottle(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a bottle and archive it."""
    storage = hass.data[DOMAIN]["storage"]
    history = storage.remove_bottle(
        msg["bottle_id"], reason=msg.get("reason", "other"), notes=msg.get("notes", "")
    )
    if history is None:
        connection.send_result(msg["id"], {"error": "Bottle not found"})
        return
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"history": history})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/restore_history",
        vol.Required("history_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_restore_history(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Restore a bottle from history."""
    storage = hass.data[DOMAIN]["storage"]
    bottle = storage.restore_history_entry(msg["history_id"])
    if bottle is None:
        connection.send_result(msg["id"], {"error": "History entry not found"})
        return
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/duplicate_bottle",
        vol.Required("bottle_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_duplicate_bottle(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Duplicate a bottle."""
    storage = hass.data[DOMAIN]["storage"]
    bottle = storage.duplicate_bottle(msg["bottle_id"])
    if bottle is None:
        connection.send_result(msg["id"], {"error": "Bottle not found"})
        return
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/move_bottle",
        vol.Required("bottle_id"): str,
        vol.Optional("location_id", default=""): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_move_bottle(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Move a bottle."""
    storage = hass.data[DOMAIN]["storage"]
    bottle = storage.move_bottle(msg["bottle_id"], msg.get("location_id", ""))
    if bottle is None:
        connection.send_result(msg["id"], {"error": "Bottle not found"})
        return
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/set_bottle_photo",
        vol.Required("bottle_id"): str,
        vol.Required("image"): str,
        vol.Optional("filename", default=""): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_bottle_photo(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Save or replace a bottle's local photo."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    bottle = storage.get_bottle(msg["bottle_id"])
    if bottle is None:
        connection.send_result(msg["id"], {"error": "Bottle not found"})
        return

    old_image_id = bottle.get("image_id", "")
    old_media = storage.media.get(old_image_id)
    shared_old_media = _image_is_referenced(
        storage, old_image_id, exclude_bottle_id=msg["bottle_id"]
    )
    reusable_media_id = old_image_id if old_image_id and not shared_old_media else None
    try:
        media_id, metadata = await media_manager.async_store_data_url(
            msg["image"],
            media_id=reusable_media_id,
            original_name=msg.get("filename", ""),
        )
        if (
            old_image_id
            and old_media
            and not shared_old_media
            and old_media.get("filename") != metadata.get("filename")
        ):
            await media_manager.async_delete_media(old_media)
        storage.upsert_media(media_id, metadata)
        bottle = storage.set_bottle_image(msg["bottle_id"], media_id)
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})
    except ValueError as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/delete_bottle_photo",
        vol.Required("bottle_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete_bottle_photo(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Delete a bottle photo."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    bottle, old_image_id = storage.delete_bottle_image(msg["bottle_id"])
    if bottle is None:
        connection.send_result(msg["id"], {"error": "Bottle not found"})
        return
    if old_image_id:
        media = storage.media.get(old_image_id)
        if not _image_is_referenced(storage, old_image_id):
            await media_manager.async_delete_media(media)
            storage.delete_media(old_image_id)
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"bottle": _with_image_url(hass, bottle)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/add_location",
        vol.Required("location"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_add_location(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Add a location."""
    storage = hass.data[DOMAIN]["storage"]
    try:
        location = storage.add_location(msg["location"])
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"location": location})
    except ValueError as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/update_location",
        vol.Required("location_id"): str,
        vol.Required("updates"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update_location(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update a location."""
    storage = hass.data[DOMAIN]["storage"]
    try:
        location = storage.update_location(msg["location_id"], msg["updates"])
        if location is None:
            connection.send_result(msg["id"], {"error": "Location not found"})
            return
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"location": location})
    except ValueError as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/remove_location",
        vol.Required("location_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_remove_location(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remove a location."""
    storage = hass.data[DOMAIN]["storage"]
    success = storage.remove_location(msg["location_id"])
    if not success:
        connection.send_result(msg["id"], {"error": "Location not found"})
        return
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "wine_cellar/get_backup"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_get_backup(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a full JSON backup including photos."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    payload = await async_create_backup_payload(storage, media_manager)
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/restore_backup",
        vol.Required("backup"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_restore_backup(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Restore a full JSON backup."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    try:
        result = await async_restore_backup_payload(
            storage, media_manager, msg["backup"]
        )
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"success": True, **result})
    except (ValueError, OSError) as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {vol.Required("type"): "wine_cellar/server_backup_save"}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_server_backup_save(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Save a full server backup."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    try:
        result = await async_save_server_backup(hass, storage, media_manager)
        connection.send_result(msg["id"], {"success": True, **result})
    except OSError as err:
        _LOGGER.warning("Failed to save wine cellar backup: %s", err)
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command(
    {vol.Required("type"): "wine_cellar/server_backup_list"}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_server_backup_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List server backups."""
    connection.send_result(
        msg["id"], {"backups": await async_list_server_backups(hass)}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/server_backup_restore",
        vol.Required("filename"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_server_backup_restore(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Restore a server backup."""
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    try:
        result = await async_restore_server_backup(
            hass, storage, media_manager, msg["filename"]
        )
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)
        connection.send_result(msg["id"], {"success": True, **result})
    except (ValueError, OSError) as err:
        connection.send_result(msg["id"], {"error": str(err)})


@websocket_api.websocket_command({vol.Required("type"): "wine_cellar/export_csv"})
@callback
def ws_export_csv(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Export bottle metadata CSV."""
    storage = hass.data[DOMAIN]["storage"]
    connection.send_result(msg["id"], {"csv": storage.export_csv()})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "wine_cellar/import_csv",
        vol.Required("csv"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_import_csv(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Import bottle metadata CSV."""
    storage = hass.data[DOMAIN]["storage"]
    count = storage.import_csv(msg["csv"])
    await storage.async_save()
    hass.bus.async_fire(EVENT_UPDATED)
    connection.send_result(msg["id"], {"imported": count})


def _public_payload(hass: HomeAssistant) -> dict[str, Any]:
    """Return storage data with local image URLs added."""
    storage = hass.data[DOMAIN]["storage"]
    return {
        "bottles": [_with_image_url(hass, bottle) for bottle in storage.bottles],
        "locations": deepcopy(storage.locations),
        "history": [_history_with_image_url(hass, entry) for entry in storage.history],
        "settings": deepcopy(storage.settings),
        "stats": storage.get_stats(),
    }


def _with_image_url(
    hass: HomeAssistant, bottle: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Add a local image URL to a bottle copy."""
    if bottle is None:
        return None
    storage = hass.data[DOMAIN]["storage"]
    media_manager = hass.data[DOMAIN]["media_manager"]
    result = deepcopy(bottle)
    result["image_url"] = media_manager.public_url(
        storage.media.get(result.get("image_id", ""))
    )
    return result


def _history_with_image_url(
    hass: HomeAssistant, entry: dict[str, Any]
) -> dict[str, Any]:
    """Add local image URL to a history entry copy."""
    result = deepcopy(entry)
    result["bottle"] = _with_image_url(hass, result.get("bottle", {})) or {}
    return result


def _image_is_referenced(
    storage: Any,
    image_id: str,
    *,
    exclude_bottle_id: str = "",
) -> bool:
    """Return whether a media id is still referenced by a bottle or history."""
    if not image_id:
        return False
    for bottle in storage.bottles:
        if bottle.get("id") == exclude_bottle_id:
            continue
        if bottle.get("image_id") == image_id:
            return True
    for entry in storage.history:
        history_bottle = entry.get("bottle", {})
        if (
            isinstance(history_bottle, dict)
            and history_bottle.get("image_id") == image_id
        ):
            return True
    return False
