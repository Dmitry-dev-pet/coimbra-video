from copy import deepcopy
import unittest

from verify_visual_polish_review import validate


CHECKPOINTS = [121, 421, 721, 1021, 1321]


def camera(frame):
    return {
        "location": [float(frame), 2.0, 3.0],
        "quaternion": [1.0, 0.0, 0.0, 0.0],
        "lens": 50.0,
        "focus_distance": 300.0,
    }


def image(frame, salt, cam):
    return {
        "output_frame": frame,
        "source_frame": 1 + (frame - 1) * 359 / 1439,
        "base_frame": int(1 + (frame - 1) * 359 / 1439),
        "subframe": 0.1,
        "camera": cam,
        "path": f"x/{frame}.png",
        "sha256": (f"{salt:02x}{frame:062x}")[-64:],
        "bytes": 100,
        "seconds": 1.0,
    }


class VisualPolishReviewTests(unittest.TestCase):
    def setUp(self):
        checkpoints = {}
        for frame in CHECKPOINTS:
            source = 1 + (frame - 1) * 359 / 1439
            checkpoints[str(frame)] = {
                "output_frame": frame,
                "source_frame": source,
                "base_frame": int(source),
                "subframe": source - int(source),
                "camera": camera(frame),
            }

        variants = {}
        settings = {
            "baseline": {
                "name": "baseline", "samples": 16, "adaptive_threshold": 0.08,
                "motion_blur": False, "motion_blur_shutter_source_frames": 0.5,
                "atmosphere_density": 0.0,
            },
            "motion_blur": {
                "name": "motion_blur", "samples": 16, "adaptive_threshold": 0.08,
                "motion_blur": True, "motion_blur_position": "CENTER",
                "motion_blur_shutter_source_frames": (359 / 1439) * 0.5,
                "motion_blur_shutter_output_frames": 0.5,
                "motion_blur_angle_degrees": 180.0,
                "atmosphere_density": 0.0,
            },
            "atmosphere_light": {
                "name": "atmosphere_light", "samples": 16, "adaptive_threshold": 0.08,
                "motion_blur": False, "motion_blur_shutter_source_frames": 0.5,
                "atmosphere_density": 0.00015, "atmosphere_anisotropy": 0.18,
                "background_strength": 0.68, "sun_energy": 1.65,
                "sun_angle_deg": 10.0, "fill_energy": 900.0,
            },
            "quality64": {
                "name": "quality64", "samples": 64, "adaptive_threshold": 0.03,
                "motion_blur": False, "motion_blur_shutter_source_frames": 0.5,
                "atmosphere_density": 0.0,
            },
        }
        for salt, name in enumerate(["baseline", "motion_blur", "atmosphere_light", "quality64"], start=1):
            variants[name] = {
                "settings": settings[name],
                "total_seconds": 5.0,
                "images": {
                    str(frame): image(frame, salt, deepcopy(checkpoints[str(frame)]["camera"]))
                    for frame in CHECKPOINTS
                },
            }

        self.receipt = {
            "version": "coimbra-035-visual-polish-review-v1",
            "source_030_run": 36720891074,
            "source_026_run": 36646652931,
            "source_030_blend_sha256": "5fe8ca9e8605c6ea1908d8a814f9ad5209248c606b34ebbbb3dd47607edff881",
            "source_030_structure_sha256": "c3e599c7d27547527c6d6b430b7aaed8c8103c297d93c68fc66eef0c194d02da",
            "accepted_lane": "Coimbra 032",
            "camera_timing_policy": "unchanged accepted 032 fractional-frame route",
            "output_fps_reference": 60,
            "output_duration_reference_seconds": 24.0,
            "checkpoint_output_frames": CHECKPOINTS,
            "checkpoint_evidence": checkpoints,
            "resolution": [1600, 1000],
            "baseline_cycles": {
                "samples": 16,
                "use_denoising": True,
                "use_adaptive_sampling": True,
                "adaptive_threshold": 0.08,
            },
            "baseline_settings": {
                "samples": 16,
                "adaptive_threshold": 0.08,
                "render_use_motion_blur": False,
            },
            "motion_blur_mapping": {
                "source_frame_step": 359 / 1439,
                "shutter_source_frames": (359 / 1439) * 0.5,
                "shutter_output_frames": 0.5,
                "shutter_angle_degrees": 180.0,
            },
            "variants": variants,
            "scene_restored": True,
            "structure_unchanged": True,
            "camera_unchanged": True,
            "promotion": "human-review-required",
        }

    def test_accept(self):
        result = validate(self.receipt)
        self.assertTrue(result["verified"])
        self.assertFalse(result["production_acceptance"])

    def test_reject_camera_change(self):
        self.receipt["variants"]["quality64"]["images"]["721"]["camera"]["lens"] = 80.0
        with self.assertRaises(ValueError):
            validate(self.receipt)

    def test_reject_wrong_shutter(self):
        self.receipt["variants"]["motion_blur"]["settings"]["motion_blur_shutter_source_frames"] = 0.5
        with self.assertRaises(ValueError):
            validate(self.receipt)

    def test_reject_combined_quality_and_blur(self):
        self.receipt["variants"]["motion_blur"]["settings"]["samples"] = 64
        with self.assertRaises(ValueError):
            validate(self.receipt)

    def test_reject_no_visible_change(self):
        baseline = self.receipt["variants"]["baseline"]["images"]
        blur = self.receipt["variants"]["motion_blur"]["images"]
        for key in list(blur)[:2]:
            blur[key]["sha256"] = baseline[key]["sha256"]
        with self.assertRaises(ValueError):
            validate(self.receipt)


if __name__ == "__main__":
    unittest.main()
