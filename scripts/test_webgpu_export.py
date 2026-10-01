from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from export_webgpu_coimbra import building_height, export_dataset, tile_of


class WebGpuExportTests(unittest.TestCase):
    def test_building_height_rules(self):
        self.assertEqual(building_height({"height": "12 m"}), 12.0)
        self.assertEqual(building_height({"building:levels": "4"}), 12.0)
        self.assertEqual(building_height({"building": "church"}), 18.0)
        self.assertEqual(building_height({"building": "yes"}), 9.0)

    def test_negative_tile_coordinates_use_floor(self):
        self.assertEqual(tile_of(-1.0, -251.0, 250.0), (-1, -2))

    def test_export_writes_real_route_and_tiles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            terrain_path = root / "terrain.npz"
            meta_path = root / "terrain.json"
            osm_path = root / "osm.json"
            contract_path = root / "contract.json"
            out = root / "out"

            xs = np.array([-300.0, -150.0, 0.0, 150.0, 300.0])
            ys = np.array([300.0, 150.0, 0.0, -150.0, -300.0])
            z = np.array(
                [
                    [110, 111, 112, 113, 114],
                    [108, 109, 110, 111, 112],
                    [106, 107, 108, 109, 110],
                    [104, 105, 106, 107, 108],
                    [102, 103, 104, 105, 106],
                ],
                dtype=float,
            )
            np.savez(terrain_path, xs=xs, ys=ys, z=z, z0=100.0)
            meta_path.write_text(
                json.dumps(
                    {
                        "source": "DGT MDT-2m",
                        "terrain_resolution_m": 6.0,
                        "bbox_wgs84": [-8.42, 40.18, -8.40, 40.20],
                    }
                )
            )
            osm_path.write_text(
                json.dumps(
                    {
                        "nodes": {
                            "1": [-40, 40],
                            "2": [40, 40],
                            "3": [40, -40],
                            "4": [-40, -40],
                            "5": [-40, 40],
                            "6": [-200, 0],
                            "7": [200, 0],
                        },
                        "ways": [
                            {
                                "id": 10,
                                "nodes": [1, 2, 3, 4, 5],
                                "tags": {"building": "yes", "building:levels": "3"},
                            },
                            {
                                "id": 20,
                                "nodes": [6, 7],
                                "tags": {"highway": "residential"},
                            },
                        ],
                    }
                )
            )
            contract_path.write_text(
                json.dumps(
                    {
                        "id": "TEST-ROUTE",
                        "expected": {
                            "camera_path": {
                                "checkpoints": [
                                    {
                                        "frame": 1,
                                        "location": [-10, 20, 30],
                                        "target": [0, 0, 0],
                                        "lens": 50,
                                    },
                                    {
                                        "frame": 60,
                                        "location": [10, -20, 25],
                                        "target": [0, 0, 0],
                                        "lens": 52,
                                    },
                                ]
                            }
                        },
                    }
                )
            )

            index = export_dataset(
                terrain_path, meta_path, osm_path, contract_path, out, 250.0
            )
            self.assertGreaterEqual(len(index["tiles"]), 4)
            self.assertEqual(index["route"]["source_contract"], "TEST-ROUTE")
            self.assertEqual(len(index["route"]["anchors"]), 2)
            self.assertTrue((out / "index.json").exists())

            tile_payloads = [
                json.loads(path.read_text()) for path in (out / "tiles").glob("*.json")
            ]
            self.assertEqual(
                sum(len(tile["buildings"]) for tile in tile_payloads), 1
            )
            self.assertGreater(
                sum(len(tile["roads"]) for tile in tile_payloads), 0
            )


if __name__ == "__main__":
    unittest.main()
