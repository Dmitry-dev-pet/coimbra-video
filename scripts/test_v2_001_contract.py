from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "coimbra_v2_001.json"


class V2001ContractTest(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads(CONFIG.read_text())

    def test_v2_has_independent_historic_core_bbox(self):
        west, south, east, north = self.cfg["bbox_wgs84"]
        self.assertLess(west, -8.437911)
        self.assertLess(south, 40.202842)
        self.assertGreater(east, -8.42596)
        self.assertGreater(north, 40.20744)

    def test_fixed_photogrammetry_source(self):
        source = self.cfg["photogrammetry"]
        self.assertEqual(
            source["model_uid"], "4175f64513a44546b65a119af5aacdff"
        )
        self.assertEqual(source["creator"], "VirtualPhoto3D")
        self.assertEqual(source["license"], "CC Attribution")

    def test_first_delivery_is_still_only(self):
        acceptance = self.cfg["acceptance"]
        hero = self.cfg["hero"]
        self.assertFalse(acceptance["full_video_allowed"])
        self.assertFalse(acceptance["motion_blur"])
        self.assertFalse(acceptance["depth_of_field"])
        self.assertFalse(acceptance["cinematic_grade"])
        self.assertEqual(hero["resolution"], [1600, 1000])
        self.assertEqual(hero["cycles_samples"], 16)


if __name__ == "__main__":
    unittest.main()
