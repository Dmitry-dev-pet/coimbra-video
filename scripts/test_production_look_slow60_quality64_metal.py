from copy import deepcopy
import unittest

from verify_production_look_slow60_quality64_metal import validate


class ProductionLookSlow60Quality64MetalTests(unittest.TestCase):
    def setUp(self):
        step = 359 / 1439
        frames = {
            str(frame): {
                "source_frame": 1.0 + (frame - 1) * step,
                "base_frame": 1,
                "subframe": 0.0,
                "sha256": "a" * 64,
                "bytes": 100,
                "seconds": 1.0,
            }
            for frame in range(1, 1441)
        }
        shards = []
        for start in range(1, 1441, 120):
            end = start + 119
            shards.append({
                "start": start,
                "end": end,
                "seconds": 120.0,
                "frames": {str(frame): deepcopy(frames[str(frame)]) for frame in range(start, end + 1)},
            })

        self.receipt = {
            "version": "coimbra-036-quality64-slow60-metal-v1",
            "source_035_review_run": 36892916114,
            "source_035_review_commit": "5a76e767d8b95578a9e999b4803176812a78b3a6",
            "quality64_review_verified": True,
            "quality64_samples": 64,
            "quality64_adaptive_threshold": 0.03,
            "source_030_run": 36720891074,
            "source_030_revision": "v2-shadow-recovery",
            "source_030_blend_sha256": "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881",
            "source_030_structure_sha256": "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da",
            "source_030_protected_sha256": "b" * 64,
            "source_026_run": 36646652931,
            "resolution": [1600, 1000],
            "source_frame_start": 1.0,
            "source_frame_end": 360.0,
            "source_frame_count": 360,
            "output_frame_count": 1440,
            "fps": 60,
            "duration_seconds": 24.0,
            "speed_ratio_vs_031": 0.5,
            "source_frame_step": step,
            "sampling": "native Blender fractional-frame evaluation",
            "repeated_frames": False,
            "optical_flow": False,
            "motion_blur": False,
            "atmosphere_light": False,
            "scene_unchanged": True,
            "structure_unchanged": True,
            "native_camera_path_unchanged": True,
            "sampling_restored": True,
            "metal": {
                "settings": {
                    "device": "GPU",
                    "compute_device_type": "METAL",
                    "metal_devices": ["Apple M4"],
                    "samples": 64,
                    "adaptive_threshold": 0.03,
                    "use_denoising": True,
                    "use_adaptive_sampling": True,
                },
                "total_seconds": 1440.0,
                "frames": frames,
                "shards": shards,
            },
        }
        self.probe = {
            "streams": [{
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 1600,
                "height": 1000,
                "r_frame_rate": "60/1",
                "nb_read_frames": "1440",
            }],
            "format": {"duration": "24.0"},
        }

    def test_accept(self):
        result = validate(self.receipt, self.probe)
        self.assertTrue(result["verified"])
        self.assertEqual(result["samples"], 64)
        self.assertTrue(result["quality64_promoted"])

    def test_reject_baseline_samples(self):
        self.receipt["metal"]["settings"]["samples"] = 16
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_review_run(self):
        self.receipt["source_035_review_run"] = 0
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_motion_blur_promotion(self):
        self.receipt["motion_blur"] = True
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_threshold(self):
        self.receipt["metal"]["settings"]["adaptive_threshold"] = 0.08
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)


if __name__ == "__main__":
    unittest.main()
