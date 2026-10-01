from copy import deepcopy
import unittest

from verify_production_look_slow60_metal import validate


class ProductionLookSlow60MetalTests(unittest.TestCase):
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
            "version": "coimbra-032-slow60-production-look-metal-v1",
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
            "scene_unchanged": True,
            "structure_unchanged": True,
            "native_camera_path_unchanged": True,
            "metal": {
                "settings": {
                    "device": "GPU",
                    "compute_device_type": "METAL",
                    "metal_devices": ["Apple M4"],
                    "samples": 16,
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
        self.assertTrue(validate(self.receipt, self.probe)["verified"])

    def test_reject_wrong_fps(self):
        self.probe["streams"][0]["r_frame_rate"] = "30/1"
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_missing_output_frame(self):
        del self.receipt["metal"]["frames"]["721"]
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_source_sample(self):
        self.receipt["metal"]["frames"]["721"]["source_frame"] += 0.5
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_repeated_frame_policy(self):
        self.receipt["repeated_frames"] = True
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_video_frames(self):
        self.probe["streams"][0]["nb_read_frames"] = "1439"
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)


if __name__ == "__main__":
    unittest.main()
