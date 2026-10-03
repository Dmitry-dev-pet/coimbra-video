import importlib.util
from pathlib import Path
import unittest

import numpy as np

MODULE = Path(__file__).with_name("build_pack.py")
spec = importlib.util.spec_from_file_location("coimbra_openttd_build", MODULE)
build = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build)


class BuildPackTests(unittest.TestCase):
    def test_square_crop_preserves_square_grid(self):
        z = np.arange(6 * 4, dtype=float).reshape(6, 4)
        xs = np.arange(4, dtype=float)
        ys = np.arange(6, dtype=float)[::-1]
        cropped, xs2, ys2, info = build.square_crop(z, xs, ys)
        self.assertEqual(cropped.shape, (4, 4))
        self.assertEqual(len(xs2), 4)
        self.assertEqual(len(ys2), 4)
        self.assertEqual(info["row0"], 1)
        self.assertEqual(info["row1"], 5)

    def test_height_conversion_marks_water_black(self):
        z = np.array([[18.0, 19.0, 20.0], [30.0, 60.0, 135.0]])
        out = build.height_to_u8(z, 19.0, 135.0)
        self.assertEqual(int(out[0, 0]), 0)
        self.assertEqual(int(out[0, 1]), 0)
        self.assertGreater(int(out[1, 0]), 0)
        self.assertEqual(int(out[1, 2]), 255)


if __name__ == "__main__":
    unittest.main()
