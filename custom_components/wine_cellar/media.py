"""Local media handling for Local Wine Cellar."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import MEDIA_DIR, MEDIA_URL, PHOTO_MIME_TYPES
from .models import utcnow

DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", re.DOTALL)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class WineCellarMediaManager:
    """Manage locally stored bottle photos."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize media manager."""
        self._hass = hass
        self.media_dir = Path(hass.config.config_dir) / MEDIA_DIR

    async def async_prepare(self) -> None:
        """Prepare local media storage."""
        await self._hass.async_add_executor_job(_ensure_dir, self.media_dir)

    def public_url(self, media: dict[str, Any] | None) -> str:
        """Return the local public URL for media metadata."""
        if not media:
            return ""
        filename = _safe_filename(media.get("filename", ""))
        if not filename:
            return ""
        version = media.get("updated_at") or media.get("created_at") or ""
        suffix = f"?v={version}" if version else ""
        return f"{MEDIA_URL}/{filename}{suffix}"

    async def async_store_data_url(
        self,
        data_url: str,
        *,
        media_id: str | None = None,
        original_name: str = "",
    ) -> tuple[str, dict[str, Any]]:
        """Store a base64 data URL locally."""
        match = DATA_URL_RE.match(data_url or "")
        if not match:
            raise ValueError("Photo must be a local image data URL")

        mime_type = match.group(1)
        extension = PHOTO_MIME_TYPES[mime_type]
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except binascii.Error as err:
            raise ValueError("Invalid photo data") from err

        if not raw:
            raise ValueError("Photo is empty")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Photo is too large")

        image_id = media_id or str(uuid.uuid4())
        filename = f"{image_id}{extension}"
        path = self.media_dir / filename

        await self._hass.async_add_executor_job(path.write_bytes, raw)

        now = utcnow()
        metadata = {
            "id": image_id,
            "filename": filename,
            "mime_type": mime_type,
            "size": len(raw),
            "original_name": str(original_name or "")[:255],
            "created_at": now,
            "updated_at": now,
        }
        return image_id, metadata

    async def async_delete_media(self, media: dict[str, Any] | None) -> None:
        """Delete media file if present."""
        if not media:
            return
        filename = _safe_filename(media.get("filename", ""))
        if not filename:
            return
        path = self.media_dir / filename
        if not _is_child(path, self.media_dir):
            return
        await self._hass.async_add_executor_job(_unlink_if_exists, path)

    async def async_export_media(self, media_map: dict[str, Any]) -> dict[str, Any]:
        """Return backup media payload with base64 file data."""
        result: dict[str, Any] = {}
        for media_id, media in media_map.items():
            filename = _safe_filename(media.get("filename", ""))
            if not filename:
                continue
            path = self.media_dir / filename
            if not _is_child(path, self.media_dir) or not path.exists():
                continue
            raw = await self._hass.async_add_executor_job(path.read_bytes)
            result[media_id] = {
                "metadata": dict(media),
                "data": base64.b64encode(raw).decode("ascii"),
            }
        return result

    async def async_restore_media(self, backup_media: dict[str, Any]) -> dict[str, Any]:
        """Restore media files from backup and return restored metadata."""
        restored: dict[str, Any] = {}
        await self._hass.async_add_executor_job(_clean_media_dir, self.media_dir)

        for media_id, payload in backup_media.items():
            if not isinstance(payload, dict):
                continue
            metadata = payload.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            mime_type = metadata.get("mime_type", "image/jpeg")
            if mime_type not in PHOTO_MIME_TYPES:
                continue
            filename = _safe_filename(metadata.get("filename", ""))
            if not filename:
                continue
            try:
                raw = base64.b64decode(str(payload.get("data", "")), validate=True)
            except binascii.Error:
                continue
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                continue
            path = self.media_dir / filename
            if not _is_child(path, self.media_dir):
                continue
            await self._hass.async_add_executor_job(path.write_bytes, raw)
            restored[media_id] = {
                "id": media_id,
                "filename": filename,
                "mime_type": mime_type,
                "size": len(raw),
                "original_name": str(metadata.get("original_name", ""))[:255],
                "created_at": metadata.get("created_at") or utcnow(),
                "updated_at": metadata.get("updated_at") or utcnow(),
            }
        return restored


def _safe_filename(filename: str) -> str:
    """Return a filename without path separators."""
    text = str(filename or "").strip()
    if "/" in text or "\\" in text or text.startswith("."):
        return ""
    if Path(text).suffix.lower() not in ALLOWED_MEDIA_SUFFIXES:
        return ""
    return text


def _is_child(path: Path, parent: Path) -> bool:
    """Return true if path resolves inside parent."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _unlink_if_exists(path: Path) -> None:
    """Delete a file if it exists."""
    if path.exists() and path.is_file():
        path.unlink()


def _clean_media_dir(path: Path) -> None:
    """Delete known local media files."""
    _ensure_dir(path)
    for item in path.iterdir():
        if item.is_file() and item.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            item.unlink()


def _ensure_dir(path: Path) -> None:
    """Create a directory if it does not already exist."""
    path.mkdir(exist_ok=True)
