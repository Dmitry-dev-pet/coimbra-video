from copy import deepcopy
import unittest

from verify_cycles_metal_checkpoints import validate


class MetalCheckpointAcceptanceTests(unittest.TestCase):
    def setUp(self):
        images = {
            str(frame): {"path": f"frame-{frame:03d}.png", "sha256": "a" * 64, "bytes": 123}
            for frame in (1, 181, 360)
        }
        timings = {"1": 2.0, "181": 2.1, "360": 1.9}
        cpu_settings = {
            "device": "CPU",
            "samples": 16,
            "use_denoising": True,
            "use_adaptive_sampling": True,
        }
        metal_settings = {
            **cpu_settings,
            "device": "GPU",
            "compute_device_type": "METAL",
            "metal_devices": ["Apple M4"],
        }
        self.receipt = {
            "version": "coimbra-027-metal-checkpoints-v1",
            "source_026_run": 36646652931,
            "blend_sha256": "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590",
            "protected_sha256": "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f",
            "resolution": [1600, 1000],
            "frames": [1, 181, 360],
            "scene_unchanged": True,
            "camera_unchanged": True,
            "cpu": {
                "settings": cpu_settings,
                "timings_seconds": timings,
                "total_seconds": 6.0,
                "images": deepcopy(images),
            },
            "metal": {
                "settings": metal_settings,
                "timings_seconds": timings,
                "total_seconds": 3.0,
                "images": deepcopy(images),
            },
            "speedup_cpu_over_metal": 2.0,
        }
        self.comparison = {
            "version": "coimbra-027-image-comparison-v1",
            "frames": {
                str(frame): {
                    "size": [1600, 1000],
                    "mean_abs_normalized": 0.01,
                    "rms_normalized": 0.02,
                    "max_abs_normalized": 0.5,
                    "diff_path": f"frame-{frame:03d}-diff-x4.png",
                }
                for frame in (1, 181, 360)
            },
        }

    def test_accept(self):
        self.assertTrue(validate(self.receipt, self.comparison)["verified"])

    def test_reject_wrong_scene(self):
        self.receipt["protected_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate(self.receipt, self.comparison)

    def test_reject_missing_metal(self):
        self.receipt["metal"]["settings"]["metal_devices"] = []
        with self.assertRaises(ValueError):
            validate(self.receipt, self.comparison)

    def test_reject_gross_visual_drift(self):
        self.comparison["frames"]["181"]["mean_abs_normalized"] = 0.5
        with self.assertRaises(ValueError):
            validate(self.receipt, self.comparison)


if __name__ == "__main__":
    unittest.main()
