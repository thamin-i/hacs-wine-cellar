"""Constants for Local Wine Cellar."""

from __future__ import annotations

DOMAIN = "wine_cellar"

STORAGE_KEY = "wine_cellar"
STORAGE_VERSION = 1

FRONTEND_VERSION = "20260521a"
FRONTEND_URL = f"/wine_cellar/wine-cellar-card-{FRONTEND_VERSION}.js"
FRONTEND_LEGACY_URL = "/wine_cellar/wine-cellar-card.js"

MEDIA_DIR = "wine_cellar_media"
MEDIA_URL = "/wine_cellar_media"
BACKUP_DIR = "wine_cellar_backups"

DATA_BOTTLES = "bottles"
DATA_LOCATIONS = "locations"
DATA_HISTORY = "history"
DATA_SETTINGS = "settings"
DATA_MEDIA = "media"

DEFAULT_SETTINGS = {
    "currency": "EUR",
    "strict_local_media": True,
}

WINE_TYPES = ("red", "white", "rosé", "sparkling", "dessert", "fortified", "other")
LOCATION_TYPES = ("rack", "fridge", "shelf", "box", "cabinet", "offsite", "other")
REMOVAL_REASONS = ("drank", "gifted", "sold", "broken", "lost", "moved", "other")

PHOTO_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

EVENT_UPDATED = f"{DOMAIN}_updated"
