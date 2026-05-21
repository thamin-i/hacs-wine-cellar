"""Regression tests for Local Wine Cellar pure data helpers."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_pure_helpers() -> types.ModuleType:
    """Load models.py without importing the Home Assistant integration package."""
    component_dir = (
        Path(__file__).resolve().parents[1] / "custom_components" / "wine_cellar"
    )
    package_name = "wine_cellar_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(component_dir)]
    sys.modules[package_name] = package

    for module_name in ("const", "models"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{module_name}", component_dir / f"{module_name}.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{package_name}.{module_name}"] = module
        spec.loader.exec_module(module)

    return sys.modules[f"{package_name}.models"]


models = _load_pure_helpers()


class WineCellarModelTests(unittest.TestCase):
    """Cover local-only inventory behavior without requiring Home Assistant."""

    def test_remote_image_url_is_rejected_without_scrubbing_notes(self) -> None:
        bottle = models.sanitize_bottle(
            {
                "id": "bottle-1",
                "name": "Chateau Local",
                "image_id": "https://example.com/bottle.jpg",
                "notes": "Bought after reading https://example.com/article",
            },
            known_location_ids=set(),
        )

        self.assertEqual(bottle["image_id"], "")
        self.assertIn("https://example.com/article", bottle["notes"])

    def test_stats_require_a_drink_window_for_ready_to_drink(self) -> None:
        bottles = [
            {
                "id": "ready",
                "wine_type": "red",
                "location_id": "rack-1",
                "estimated_value": 25,
                "drink_from": 2020,
                "drink_by": 2030,
            },
            {
                "id": "past",
                "wine_type": "white",
                "location_id": "rack-1",
                "estimated_value": 10,
                "drink_by": 2024,
            },
            {
                "id": "unknown",
                "wine_type": "sparkling",
                "location_id": "",
                "estimated_value": 15,
            },
        ]
        locations = [{"id": "rack-1", "capacity": 12}]

        stats = models.compute_stats(bottles, locations, current_year=2026)

        self.assertEqual(stats["total_bottles"], 3)
        self.assertEqual(stats["ready_to_drink"], 1)
        self.assertEqual(stats["past_peak"], 1)
        self.assertEqual(stats["unassigned_bottles"], 1)
        self.assertEqual(stats["total_value"], 50)

    def test_csv_round_trip_maps_location_names(self) -> None:
        locations = [{"id": "rack-1", "name": "Main Rack"}]
        bottles = [
            models.sanitize_bottle(
                {
                    "id": "bottle-1",
                    "name": "Local Syrah",
                    "producer": "Cellar Door",
                    "tags": ["weekday", "bbq"],
                    "location_id": "rack-1",
                },
                known_location_ids={"rack-1"},
            )
        ]

        rows = models.import_csv(models.export_csv(bottles, locations), locations)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["location_id"], "rack-1")
        self.assertEqual(rows[0]["location_name"], "Main Rack")
        self.assertEqual(rows[0]["tags"], "weekday, bbq")

    def test_normalize_strips_unknown_locations_and_remote_images(self) -> None:
        data = {
            "locations": [{"id": "known", "name": "Known Rack"}],
            "bottles": [
                {
                    "id": "bottle-1",
                    "name": "Offline Bottle",
                    "location_id": "missing",
                    "image_id": "http://example.invalid/remote.png",
                }
            ],
        }

        normalized = models.normalize_data(data)

        self.assertEqual(normalized["bottles"][0]["location_id"], "")
        self.assertEqual(normalized["bottles"][0]["image_id"], "")

    def test_blank_data_shape(self) -> None:
        data = models.blank_data()

        self.assertEqual(data["bottles"], [])
        self.assertEqual(data["locations"], [])
        self.assertEqual(data["history"], [])
        self.assertEqual(data["media"], {})
        self.assertEqual(data["settings"]["currency"], "EUR")
        self.assertTrue(data["settings"]["strict_local_media"])

    def test_normalize_garbage_payload_returns_blank(self) -> None:
        self.assertEqual(models.normalize_data(None), models.blank_data())
        self.assertEqual(models.normalize_data("nope"), models.blank_data())  # type: ignore[arg-type]
        self.assertEqual(models.normalize_data([]), models.blank_data())  # type: ignore[arg-type]

    def test_sanitize_location_falls_back_to_defaults(self) -> None:
        location = models.sanitize_location(
            {
                "id": "loc-1",
                "name": "  ",
                "location_type": "spaceship",
                "capacity": -5,
                "notes": "x" * 5000,
            }
        )

        self.assertEqual(location["name"], "Unnamed location")
        self.assertEqual(location["location_type"], "rack")
        self.assertEqual(location["capacity"], 0)
        self.assertEqual(len(location["notes"]), 1000)

    def test_sanitize_location_requires_id(self) -> None:
        with self.assertRaises(ValueError):
            models.sanitize_location({"name": "no id"})

    def test_sanitize_bottle_clamps_invalid_fields(self) -> None:
        bottle = models.sanitize_bottle(
            {
                "id": "bottle-x",
                "name": "Edge Case",
                "vintage": "not-a-year",
                "drink_from": 1800,
                "drink_by": 2300,
                "rating": 12,
                "purchase_price": -42,
                "wine_type": "??",
                "tags": "alpha, beta, alpha, gamma",
                "image_id": "https://remote/img.png",
            },
            known_location_ids=set(),
        )

        self.assertIsNone(bottle["vintage"])
        self.assertIsNone(bottle["drink_from"])
        self.assertIsNone(bottle["drink_by"])
        self.assertIsNone(bottle["rating"])
        self.assertIsNone(bottle["purchase_price"])
        self.assertEqual(bottle["wine_type"], "red")
        self.assertEqual(bottle["tags"], ["alpha", "beta", "gamma"])
        self.assertEqual(bottle["image_id"], "")

    def test_sanitize_bottle_requires_id(self) -> None:
        with self.assertRaises(ValueError):
            models.sanitize_bottle({"name": "Anon"}, known_location_ids=set())

    def test_sanitize_history_entry_falls_back_to_defaults(self) -> None:
        entry = models.sanitize_history_entry(
            {"id": "h1", "bottle": "not-a-dict", "reason": "yeeted"}
        )

        self.assertEqual(entry["reason"], "other")
        self.assertEqual(entry["bottle"]["id"], None)
        self.assertTrue(entry["removed_at"])

    def test_stats_capacity_percentage(self) -> None:
        bottles = [
            {"id": str(i), "location_id": "rack", "wine_type": "red"} for i in range(3)
        ]
        locations = [{"id": "rack", "capacity": 10}]

        stats = models.compute_stats(bottles, locations, current_year=2026)

        self.assertEqual(stats["total_capacity"], 10)
        self.assertEqual(stats["capacity_used"], 30.0)
        self.assertEqual(stats["available_slots"], 7)
        self.assertEqual(stats["by_location"], {"rack": 3})

    def test_import_csv_skips_rows_without_name(self) -> None:
        csv_text = (
            "name,producer,vintage,location_name\n"
            ",NoName Producer,2020,\n"
            "Has Name,Producer,2021,Main Rack\n"
        )
        locations = [{"id": "rack-1", "name": "Main Rack"}]

        rows = models.import_csv(csv_text, locations)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Has Name")
        self.assertEqual(rows[0]["location_id"], "rack-1")


if __name__ == "__main__":
    unittest.main()
