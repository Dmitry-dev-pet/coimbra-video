from copy import deepcopy
import unittest

from verify_cycles_metal_full_route import validate


class MetalFullRouteAcceptanceTests(unittest.TestCase):
    def setUp(self):
        frames = {
            str(frame): {"sha256": "a" * 64, "bytes": 100, "seconds": 1.0}
            for frame in range(1, 361)
        }
        shards = []
        for start in range(1, 361, 30):
            end = start + 29
            shards.append({
                "start": start,
                "end": end,
                "seconds": 30.0,
                "frames": {str(frame): deepcopy(frames[str(frame)]) for frame in range(start, end + 1)},
            })
        self.receipt = {
            "version": "coimbra-028-metal-full-route-v1",
            "source_026_run": 36646652931,
            "source_025_commit": "d178382d10eef41ec00da3fe562fcc445438f8da",
            "blend_sha256": "5eed3da289693015ed6b491eb26f992f0c579a1625540f1f4acc13155860a590",
            "protected_sha256": "98ee88d4c6e28dfccb010b7ad9faa89f88466768eed7ec440fb96d99b276450f",
            "resolution": [1600, 1000],
            "frame_count": 360,
            "fps": 30,
            "duration_seconds": 12.0,
            "scene_unchanged": True,
            "camera_unchanged": True,
            "metal": {
                "settings": {
                    "device": "GPU",
                    "compute_device_type": "METAL",
                    "metal_devices": ["Apple M4"],
                    "samples": 16,
                    "use_denoising": True,
                    "use_adaptive_sampling": True,
                },
                "total_seconds": 360.0,
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
                "r_frame_rate": "30/1",
                "nb_read_frames": "360",
            }],
            "format": {"duration": "12.0"},
        }

    def test_accept(self):
        self.assertTrue(validate(self.receipt, self.probe)["verified"])

    def test_reject_missing_frame(self):
        del self.receipt["metal"]["frames"]["181"]
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_shard(self):
        self.receipt["metal"]["shards"][3]["start"] = 90
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_cpu(self):
        self.receipt["metal"]["settings"]["device"] = "CPU"
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_wrong_video_frames(self):
        self.probe["streams"][0]["nb_read_frames"] = "359"
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)

    def test_reject_scene_mutation(self):
        self.receipt["protected_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate(self.receipt, self.probe)


if __name__ == "__main__":
    unittest.main()
