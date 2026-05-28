from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ai import build_analysis_summary, classify_alarm_causes, generate_test_conclusion, water_stats
from app.cache import LocalCache
from app.simulator import alarms_from_records, history, sample_devices


class CoreLogicTest(unittest.TestCase):
    def test_simulator_generates_status_and_alarms(self) -> None:
        device = sample_devices()[0]
        records = history(device, 120)
        alarms = alarms_from_records(device, records)
        self.assertEqual(len(records), 120)
        self.assertGreater(len(alarms), 0)
        self.assertTrue({0, 1, 2}.issuperset({int(record["status"]) for record in records}))

    def test_ai_analysis_summary(self) -> None:
        device = sample_devices()[0]
        records = history(device, 120)
        alarms = alarms_from_records(device, records)
        stats = water_stats(records)
        summary = build_analysis_summary(records, device)
        self.assertEqual(stats["count"], 120)
        self.assertIn("danger_margin", summary)
        self.assertIn("报警原因分类", classify_alarm_causes(device, records, alarms))
        self.assertIn("测试结论", generate_test_conclusion(device, records, alarms))

    def test_cache_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = LocalCache(Path(tmp) / "cache.sqlite3")
            device = sample_devices()[0]
            records = history(device, 20)
            cache.save_devices([device])
            cache.save_water_levels(records)
            cache.save_alarms(alarms_from_records(device, records))
            counts = cache.table_counts()
            self.assertEqual(counts["devices"], 1)
            self.assertEqual(counts["water_levels"], 20)
            removed = cache.cleanup_water_levels(keep=5)
            self.assertEqual(removed, 15)
            cache.vacuum()


if __name__ == "__main__":
    unittest.main()
