import json
from pathlib import Path
import tempfile
import unittest

from summarize_cycles_render_benchmark import summarize


class BenchmarkSummaryTests(unittest.TestCase):
    def write_receipt(self, root, folder, mode, start, end, total):
        path = root / folder
        path.mkdir(parents=True)
        frames = range(start, end + 1)
        payload = {
            "version": "coimbra-029-device-benchmark-v1",
            "device_mode": mode,
            "start": start,
            "end": end,
            "frame_count": end - start + 1,
            "scene_unchanged": True,
            "camera_unchanged": True,
            "total_seconds": total,
            "timings_seconds": {str(f): 1.0 for f in frames},
            "images": {str(f): {"sha256": "a" * 64, "bytes": 10} for f in frames},
        }
        (path / "receipt.json").write_text(json.dumps(payload))

    def test_summary_selects_fastest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_receipt(root, "mac-cpu", "cpu", 181, 210, 300.0)
            self.write_receipt(root, "metal-1x", "metal", 181, 210, 180.0)
            self.write_receipt(root, "metal-cpu", "metal-cpu", 181, 210, 170.0)
            self.write_receipt(root, "metal-2x-a", "metal", 181, 195, 100.0)
            self.write_receipt(root, "metal-2x-b", "metal", 196, 210, 95.0)
            (root / "metal-2x-wall.json").write_text(json.dumps({"wall_seconds": 110.0}))
            result = summarize(root)
            self.assertEqual(result["fastest_mac_mode"], "mac_metal_2x")
            self.assertGreater(result["metal_2x_speedup_vs_metal_1x"], 1.0)

    def test_reject_incomplete_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_receipt(root, "mac-cpu", "cpu", 181, 209, 300.0)
            self.write_receipt(root, "metal-1x", "metal", 181, 210, 180.0)
            self.write_receipt(root, "metal-cpu", "metal-cpu", 181, 210, 170.0)
            self.write_receipt(root, "metal-2x-a", "metal", 181, 195, 100.0)
            self.write_receipt(root, "metal-2x-b", "metal", 196, 210, 95.0)
            (root / "metal-2x-wall.json").write_text(json.dumps({"wall_seconds": 110.0}))
            with self.assertRaises(ValueError):
                summarize(root)


if __name__ == "__main__":
    unittest.main()
