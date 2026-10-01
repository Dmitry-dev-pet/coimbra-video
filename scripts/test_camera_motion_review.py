from copy import deepcopy
import unittest

from verify_camera_motion_review import validate


def metric(cv=0.1):
    return {"mean": 1.0, "std": cv, "cv": cv, "p50": 1.0, "p95": 1.1, "max": 1.2}


class CameraMotionReviewTests(unittest.TestCase):
    def setUp(self):
        anchors = []
        for index, frame in enumerate([1, 61, 121, 181, 241, 301, 360]):
            anchors.append({
                "source_frame": frame,
                "location": [float(index), 0.0, 1.0],
                "target": [float(index), 1.0, 1.0],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "lens": 50.0,
                "focus_distance": 300.0,
            })
        records = []
        for frame in range(1, 1441):
            t = (frame - 1) / 1439
            records.append({
                "output_frame": frame,
                "route_fraction": t,
                "location": [6.0 * t, 0.0, 1.0],
                "target": [6.0 * t, 1.0, 1.0],
                "quaternion": [1.0, 0.0, 0.0, 0.0],
                "lens": 50.0,
                "focus_distance": 300.0,
            })

        current = {
            "linear_step": metric(0.2),
            "angular_step_radians": metric(0.2),
            "linear_step_change": metric(0.2),
            "angular_step_change_radians": metric(0.2),
        }
        smooth = {
            "linear_step": metric(0.001),
            "angular_step_radians": metric(0.1),
            "linear_step_change": metric(0.001),
            "angular_step_change_radians": metric(0.1),
        }

        self.receipt = {
            "version": "coimbra-033-smooth-camera-motion-review-v1",
            "source_030_run": 36720891074,
            "source_030_revision": "v2-shadow-recovery",
            "source_030_blend_sha256": "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881",
            "source_030_structure_sha256": "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da",
            "source_026_run": 36646652931,
            "anchor_source_frames": [1, 61, 121, 181, 241, 301, 360],
            "anchors": anchors,
            "route_model": {
                "position": "centripetal Catmull-Rom through accepted anchor locations",
                "target": "centripetal Catmull-Rom through anchor forward targets",
                "speed": "global arc-length parameterization",
                "rotation": "look-at quaternion derived from smoothed target and position",
                "lens_focus": "cubic interpolation",
                "path_length": 6.0,
                "segment_lengths": [1.0] * 6,
                "segment_time_seconds": [4.0] * 6,
            },
            "delivery": {
                "frame_count": 1440,
                "fps": 60,
                "duration_seconds": 24.0,
                "resolution": [960, 600],
                "purpose": "motion-only proxy review; not a production-look acceptance render",
                "motion_blur": False,
            },
            "motion_metrics": {
                "current_032_sampling": current,
                "candidate_033_smoothed": smooth,
            },
            "scene_structure_unchanged": True,
            "native_camera_animation_unchanged": True,
            "proxy": {
                "engine": "BLENDER_EEVEE_NEXT",
                "resolution": [960, 600],
                "fps": 60,
                "frame_count": 1440,
                "total_seconds": 100.0,
                "frames": {str(i): {"sha256": "a" * 64, "bytes": 1, "seconds": 0.1} for i in range(1, 1441)},
            },
            "smooth_records": records,
        }
        self.proxy_probe = {
            "streams": [{
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
                "width": 960,
                "height": 600,
                "r_frame_rate": "60/1",
                "nb_read_frames": "1440",
            }],
            "format": {"duration": "24.0"},
        }

    def test_accept(self):
        result = validate(self.receipt, self.proxy_probe)
        self.assertTrue(result["verified"])
        self.assertFalse(result["production_acceptance"])

    def test_reject_nonconstant_translation(self):
        self.receipt["motion_metrics"]["candidate_033_smoothed"]["linear_step"]["cv"] = 0.05
        with self.assertRaises(ValueError):
            validate(self.receipt, self.proxy_probe)

    def test_reject_camera_mutation(self):
        self.receipt["native_camera_animation_unchanged"] = False
        with self.assertRaises(ValueError):
            validate(self.receipt, self.proxy_probe)

    def test_reject_wrong_fps(self):
        self.proxy_probe["streams"][0]["r_frame_rate"] = "30/1"
        with self.assertRaises(ValueError):
            validate(self.receipt, self.proxy_probe)


if __name__ == "__main__":
    unittest.main()
