from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from verify_production_look_review import verify


class ProductionLookVerificationTests(unittest.TestCase):
    def fixture(self, root: Path, delta: int = 20) -> None:
        baseline = (90, 100, 110)
        candidate = (90 + delta, 100, 110)
        for frame in (1, 181, 360):
            Image.new("RGB", (1600, 1000), baseline).save(root / f"frame-{frame:03d}-baseline.png")
            Image.new("RGB", (1600, 1000), candidate).save(root / f"frame-{frame:03d}-candidate.png")
        (root / "coimbra-production-look.blend").write_bytes(b"x" * (1024 * 1024 + 1))
        manifest = {
            "version": "coimbra-030-production-look-review-v1",
            "review_frames": [1, 181, 360],
            "resolution": [1600, 1000],
            "structure_unchanged": True,
            "camera_unchanged": True,
            "promotion": "review-required",
            "changes": {"materials": [{"material": "Semantic_Leaves_A"}], "lights": [{}, {}]},
            "baseline": {
                str(frame): {"path": f"frame-{frame:03d}-baseline.png"}
                for frame in (1, 181, 360)
            },
            "candidate": {
                str(frame): {"path": f"frame-{frame:03d}-candidate.png"}
                for frame in (1, 181, 360)
            },
            "candidate_blend": {
                "path": "coimbra-production-look.blend",
                "sha256": "a" * 64,
            },
        }
        (root / "production-look-review.json").write_text(json.dumps(manifest))

    def test_accepts_bounded_visible_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, delta=20)
            result = verify(root)
            self.assertTrue(result["verified"])
            self.assertTrue(result["review_required"])

    def test_rejects_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, delta=0)
            with self.assertRaises(ValueError):
                verify(root)


if __name__ == "__main__":
    unittest.main()
