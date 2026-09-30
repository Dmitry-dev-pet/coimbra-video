from copy import deepcopy
import unittest
from verify_cycles_full_route import validate


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.p = {"version": "coimbra-cycles-full-route-prepare-v1", "geometry_matches_025": True,
                  "frame_count": 360, "fps": 30, "resolution": [1600, 1000],
                  "source_025_commit": "d178382d10eef41ec00da3fe562fcc445438f8da",
                  "cameras": [{"frame": f} for f in range(1, 361)],
                  "protected_sha256": "a" * 64, "blend_sha256": "b" * 64,
                  "cycles": {"device": "CPU", "samples": 16, "use_denoising": True,
                             "use_adaptive_sampling": True}}
        self.shards = [{"start": s, "end": s + 29, "protected_sha256": "a" * 64,
                        "blend_sha256": "b" * 64, "cycles": deepcopy(self.p["cycles"]),
                        "camera_unchanged": True, "geometry_material_world_unchanged": True,
                        "frames": {str(f): "c" * 64 for f in range(s, s + 30)}}
                       for s in range(1, 361, 30)]
        self.probe = {"streams": [{"codec_name": "h264", "pix_fmt": "yuv420p", "width": 1600,
                                  "height": 1000, "r_frame_rate": "30/1", "nb_read_frames": "360"}],
                      "format": {"duration": "12.0"}}

    def test_accept_complete(self):
        self.assertTrue(validate(self.p, self.shards, self.probe)["verified"])

    def test_reject_scene_mutation(self):
        self.shards[0]["protected_sha256"] = "d" * 64
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_missing_shard(self):
        with self.assertRaises(ValueError): validate(self.p, self.shards[:-1], self.probe)

    def test_reject_duplicate_shard(self):
        self.shards[-1] = deepcopy(self.shards[0])
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_camera_change(self):
        self.shards[3]["camera_unchanged"] = False
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_timing_change(self):
        self.probe["format"]["duration"] = "48.0"
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_eevee(self):
        self.shards[2]["cycles"]["samples"] = 128
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_missing_frame(self):
        del self.shards[0]["frames"]["1"]
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)

    def test_reject_cropped_framing(self):
        self.probe["streams"][0]["height"] = 900
        with self.assertRaises(ValueError): validate(self.p, self.shards, self.probe)


if __name__ == "__main__":
    unittest.main()
