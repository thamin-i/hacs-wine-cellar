"""Local Wine Cellar integration."""
# pylint: disable=invalid-name,import-outside-toplevel,broad-exception-caught

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .backup import async_restore_server_backup, async_save_server_backup
from .const import (
    DOMAIN,
    EVENT_UPDATED,
    FRONTEND_LEGACY_URL,
    FRONTEND_URL,
    MEDIA_URL,
    REMOVAL_REASONS,
    WINE_TYPES,
)
from .media import WineCellarMediaManager
from .storage import WineCellarStorage
from .websocket import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_ADD_BOTTLE = "add_bottle"
SERVICE_UPDATE_BOTTLE = "update_bottle"
SERVICE_REMOVE_BOTTLE = "remove_bottle"
SERVICE_MOVE_BOTTLE = "move_bottle"
SERVICE_DUPLICATE_BOTTLE = "duplicate_bottle"
SERVICE_CREATE_BACKUP = "create_backup"
SERVICE_RESTORE_BACKUP = "restore_backup"
SERVICES = (
    SERVICE_ADD_BOTTLE,
    SERVICE_UPDATE_BOTTLE,
    SERVICE_REMOVE_BOTTLE,
    SERVICE_MOVE_BOTTLE,
    SERVICE_DUPLICATE_BOTTLE,
    SERVICE_CREATE_BACKUP,
    SERVICE_RESTORE_BACKUP,
)


async def async_setup(hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Set up Local Wine Cellar integration services."""
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Local Wine Cellar from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    storage = WineCellarStorage(hass)
    await storage.async_load()
    media_manager = WineCellarMediaManager(hass)
    await media_manager.async_prepare()

    domain_data["storage"] = storage
    domain_data["media_manager"] = media_manager
    domain_data["entry"] = entry

    if not domain_data.get("static_registered"):
        await _register_static_paths(hass, media_manager)
        _register_frontend_resource(hass)
        domain_data["static_registered"] = True

    if not domain_data.get("websocket_registered"):
        async_register_websocket_commands(hass)
        domain_data["websocket_registered"] = True

    _register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Local Wine Cellar."""
    unload_ok = bool(await hass.config_entries.async_unload_platforms(entry, PLATFORMS))
    if unload_ok:
        for service in SERVICES:
            hass.services.async_remove(DOMAIN, service)
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop("storage", None)
        domain_data.pop("media_manager", None)
        domain_data.pop("entry", None)
    return unload_ok


async def _register_static_paths(
    hass: HomeAssistant,
    media_manager: WineCellarMediaManager,
) -> None:
    """Register local frontend and media static paths."""
    frontend_path = str(Path(__file__).parent / "frontend" / "wine-cellar-card.js")
    media_path = str(media_manager.media_dir)
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(FRONTEND_URL, frontend_path, False),
                StaticPathConfig(FRONTEND_LEGACY_URL, frontend_path, False),
                StaticPathConfig(MEDIA_URL, media_path, False),
            ]
        )
    except (ImportError, AttributeError, TypeError):
        legacy_register = getattr(hass.http, "register_static_path")
        legacy_register(FRONTEND_URL, frontend_path, cache_headers=False)
        legacy_register(FRONTEND_LEGACY_URL, frontend_path, cache_headers=False)
        legacy_register(MEDIA_URL, media_path, cache_headers=False)


def _register_frontend_resource(hass: HomeAssistant) -> None:
    """Register the Lovelace card resource if the API is available."""
    try:
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )
    except ImportError:
        return

    async def _async_add_resource(*_args: Any) -> None:
        lovelace_data = hass.data.get("lovelace", {})
        resources: ResourceStorageCollection | None = lovelace_data.get(
            "resources"
        ) or hass.data.get("lovelace_resources")
        if resources is None:
            return
        if not hasattr(resources, "async_items") or not hasattr(
            resources, "async_create_item"
        ):
            return
        existing = None
        for item in resources.async_items():
            if "/wine_cellar/wine-cellar-card" in item.get("url", ""):
                existing = item
                break
        try:
            if existing and existing.get("url") != FRONTEND_URL:
                await resources.async_update_item(existing["id"], {"url": FRONTEND_URL})
            elif not existing:
                await resources.async_create_item(
                    {"res_type": "module", "url": FRONTEND_URL}
                )
        except Exception as err:
            _LOGGER.debug("Could not auto-register wine cellar card resource: %s", err)

    if hass.is_running:
        hass.async_create_task(_async_add_resource())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_add_resource)


def _register_services(hass: HomeAssistant) -> None:
    """Register Home Assistant services."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_BOTTLE):
        return

    async def handle_add_bottle(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        bottle = storage.add_bottle(dict(call.data))
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED, {"bottle_id": bottle["id"]})

    async def handle_update_bottle(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        bottle_id = call.data["bottle_id"]
        updates = dict(call.data.get("updates", {}))
        for key, value in call.data.items():
            if key not in ("bottle_id", "updates"):
                updates[key] = value
        bottle = storage.update_bottle(bottle_id, updates)
        if bottle:
            await storage.async_save()
            hass.bus.async_fire(EVENT_UPDATED, {"bottle_id": bottle_id})

    async def handle_remove_bottle(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        history = storage.remove_bottle(
            call.data["bottle_id"],
            reason=call.data.get("reason", "other"),
            notes=call.data.get("notes", ""),
        )
        if history:
            await storage.async_save()
            hass.bus.async_fire(EVENT_UPDATED, {"history_id": history["id"]})

    async def handle_move_bottle(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        bottle = storage.move_bottle(
            call.data["bottle_id"], call.data.get("location_id", "")
        )
        if bottle:
            await storage.async_save()
            hass.bus.async_fire(EVENT_UPDATED, {"bottle_id": call.data["bottle_id"]})

    async def handle_duplicate_bottle(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        bottle = storage.duplicate_bottle(call.data["bottle_id"])
        if bottle:
            await storage.async_save()
            hass.bus.async_fire(EVENT_UPDATED, {"bottle_id": bottle["id"]})

    async def handle_create_backup(_call: ServiceCall) -> None:
        storage = _get_storage(hass)
        media_manager = _get_media_manager(hass)
        await async_save_server_backup(hass, storage, media_manager)

    async def handle_restore_backup(call: ServiceCall) -> None:
        storage = _get_storage(hass)
        media_manager = _get_media_manager(hass)
        await async_restore_server_backup(
            hass, storage, media_manager, call.data["filename"]
        )
        await storage.async_save()
        hass.bus.async_fire(EVENT_UPDATED)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_BOTTLE,
        handle_add_bottle,
        schema=_bottle_service_schema(require_name=True),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_BOTTLE,
        handle_update_bottle,
        schema=vol.Schema(
            {
                vol.Required("bottle_id"): cv.string,
                vol.Optional("updates"): dict,
                **_bottle_optional_fields(),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_BOTTLE,
        handle_remove_bottle,
        schema=vol.Schema(
            {
                vol.Required("bottle_id"): cv.string,
                vol.Optional("reason", default="other"): vol.In(REMOVAL_REASONS),
                vol.Optional("notes", default=""): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MOVE_BOTTLE,
        handle_move_bottle,
        schema=vol.Schema(
            {
                vol.Required("bottle_id"): cv.string,
                vol.Optional("location_id", default=""): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DUPLICATE_BOTTLE,
        handle_duplicate_bottle,
        schema=vol.Schema({vol.Required("bottle_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_BACKUP,
        handle_create_backup,
        schema=vol.Schema({}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTORE_BACKUP,
        handle_restore_backup,
        schema=vol.Schema({vol.Required("filename"): cv.string}),
    )


def _bottle_service_schema(*, require_name: bool) -> vol.Schema:
    fields = _bottle_optional_fields(include_name=not require_name)
    if require_name:
        fields[vol.Required("name")] = cv.string
    return vol.Schema(fields)


def _bottle_optional_fields(*, include_name: bool = True) -> dict[Any, Any]:
    fields: dict[Any, Any] = {
        vol.Optional("producer"): cv.string,
        vol.Optional("vintage"): vol.Coerce(int),
        vol.Optional("wine_type"): vol.In(WINE_TYPES),
        vol.Optional("country"): cv.string,
        vol.Optional("region"): cv.string,
        vol.Optional("appellation"): cv.string,
        vol.Optional("grapes"): cv.string,
        vol.Optional("bottle_size"): cv.string,
        vol.Optional("purchase_price"): vol.Coerce(float),
        vol.Optional("estimated_value"): vol.Coerce(float),
        vol.Optional("purchase_date"): cv.string,
        vol.Optional("drink_from"): vol.Coerce(int),
        vol.Optional("drink_by"): vol.Coerce(int),
        vol.Optional("rating"): vol.Coerce(float),
        vol.Optional("notes"): cv.string,
        vol.Optional("tags"): vol.Any([cv.string], cv.string),
        vol.Optional("barcode"): cv.string,
        vol.Optional("location_id"): cv.string,
    }
    if include_name:
        fields[vol.Optional("name")] = cv.string
    return fields


def _get_storage(hass: HomeAssistant) -> WineCellarStorage:
    """Return loaded wine cellar storage or raise a service-friendly error."""
    storage = hass.data.get(DOMAIN, {}).get("storage")
    if storage is None:
        raise HomeAssistantError("Local Wine Cellar is not loaded")
    return cast(WineCellarStorage, storage)


def _get_media_manager(hass: HomeAssistant) -> WineCellarMediaManager:
    """Return loaded wine cellar media manager or raise a service-friendly error."""
    media_manager = hass.data.get(DOMAIN, {}).get("media_manager")
    if media_manager is None:
        raise HomeAssistantError("Local Wine Cellar is not loaded")
    return cast(WineCellarMediaManager, media_manager)
