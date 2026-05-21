# Local Wine Cellar

Local Wine Cellar is a Home Assistant custom integration for managing wine bottles from a dashboard without any external wine APIs.

It is intentionally local-only:

- no Vivino
- no Open Food Facts
- no AI services
- no analytics
- no cloud sync
- no outbound HTTP calls

## Features

- Add, edit, duplicate, move, and remove individual physical bottles
- Track locations such as racks, fridges, shelves, boxes, cabinets, offsite storage, and other areas
- Save local bottle photos from a phone camera or file upload
- Search, filter, and sort inventory
- View ready-to-drink and past-peak bottles from manually entered drink windows
- Keep removal history with reasons
- Create JSON backups that include local photos
- Import and export bottle metadata as CSV
- Expose Home Assistant sensors and services for automations

## Installation

### HACS Custom Repository

1. Open HACS.
2. Add this repository as a custom repository with category `Integration`.
3. Install **Local Wine Cellar**.
4. Restart Home Assistant.
5. Go to **Settings > Devices & services > Add Integration**.
6. Search for **Local Wine Cellar**.
7. Add the card to a dashboard:

```yaml
type: custom:wine-cellar-card
title: Wine Cellar
```

The integration attempts to register the Lovelace resource automatically. If the card is not found, add this dashboard resource manually:

```yaml
url: /wine_cellar/wine-cellar-card-20260521a.js
type: module
```

### Manual

Copy `custom_components/wine_cellar` into your Home Assistant `custom_components` directory and restart Home Assistant.

## Storage

Bottle metadata is stored with Home Assistant's storage helper. Photos are stored under:

```text
config/wine_cellar_media/
```

Server-side backups are stored under:

```text
config/wine_cellar_backups/
```

## Services

- `wine_cellar.add_bottle`
- `wine_cellar.update_bottle`
- `wine_cellar.remove_bottle`
- `wine_cellar.move_bottle`
- `wine_cellar.duplicate_bottle`
- `wine_cellar.create_backup`
- `wine_cellar.restore_backup`

CSV and JSON upload/download workflows are handled through the Lovelace card.

## Sensors

- `sensor.wine_cellar_total_bottles`
- `sensor.wine_cellar_total_value`
- `sensor.wine_cellar_ready_to_drink`
- `sensor.wine_cellar_past_peak`
- `sensor.wine_cellar_capacity_used`
- `sensor.wine_cellar_unassigned_bottles`
- per-location bottle count sensors

## Privacy

This integration rejects remote image URLs and stores only local media uploaded through Home Assistant. It does not use any external lookup providers.

## V1 Scope

V1 is list-based inventory and location management. It intentionally excludes Vivino, Open Food Facts, AI lookup, barcode lookup, visual rack grids, QR labels, analytics, and cloud sync.
