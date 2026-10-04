import unittest

from openttd.build_osm_building_plan import closest_town_name


class ClosestTownNameTests(unittest.TestCase):
    def test_uses_manhattan_distance_like_openttd_15_3(self):
        towns = {
            "Manhattan winner": {"x": 0, "y": 6, "source_order": 0},
            "Euclidean winner": {"x": 4, "y": 4, "source_order": 1},
        }
        candidate = {"x": 0, "y": 0}
        self.assertEqual(closest_town_name(candidate, towns), "Manhattan winner")

    def test_tie_breaks_by_source_town_order(self):
        towns = {
            "First town": {"x": 0, "y": 2, "source_order": 0},
            "Second town": {"x": 2, "y": 0, "source_order": 1},
        }
        candidate = {"x": 0, "y": 0}
        self.assertEqual(closest_town_name(candidate, towns), "First town")


if __name__ == "__main__":
    unittest.main()
