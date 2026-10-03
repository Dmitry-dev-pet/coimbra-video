import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name("build_road_plan.py")
spec = importlib.util.spec_from_file_location("coimbra_road_plan", MODULE)
road = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(road)


class RoadPlanTests(unittest.TestCase):
    def test_manhattan_is_four_connected(self):
        path = road.manhattan_segment((2, 3), (8, 7))
        self.assertEqual(path[0], (2, 3))
        self.assertEqual(path[-1], (8, 7))
        for a, b in zip(path, path[1:]):
            self.assertEqual(abs(a[0]-b[0]) + abs(a[1]-b[1]), 1)

    def test_compress_produces_straight_runs(self):
        cells = [(1,1), (2,1), (3,1), (3,2), (3,3)]
        runs = road.compress_cells(cells)
        self.assertEqual(runs, [((1,1), (3,1)), ((3,1), (3,3))])

    def test_grade_separation_classification(self):
        cfg = {"bridge_from_positive_layer": True, "tunnel_from_negative_layer": True}
        self.assertEqual(road.classify_structure({"bridge": "yes"}, cfg)[0], "bridge")
        self.assertEqual(road.classify_structure({"tunnel": "yes"}, cfg)[0], "tunnel")
        self.assertEqual(road.classify_structure({"layer": "1"}, cfg)[0], "bridge")
        self.assertEqual(road.classify_structure({"layer": "-1"}, cfg)[0], "tunnel")
        self.assertEqual(road.classify_structure({}, cfg)[0], "ground")

    def test_merge_ground_edges_to_runs_preserves_exact_edges(self):
        edges = [
            {"start": [1, 2], "end": [2, 2]},
            {"start": [2, 2], "end": [3, 2]},
            {"start": [3, 2], "end": [4, 2]},
            {"start": [3, 1], "end": [3, 2]},
            {"start": [3, 2], "end": [3, 3]},
        ]
        runs = road.merge_ground_edges_to_runs(edges)
        self.assertEqual(sorted(runs), sorted([
            [1, 2, 4, 2],
            [3, 1, 3, 3],
        ]))



if __name__ == "__main__":
    unittest.main()
