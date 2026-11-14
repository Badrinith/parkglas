import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import check_snapshot as c


def snap(car=5000, fuel=1000, charger=800, bay=500, street=100):
    kinds = [("carPark", car), ("fuel", fuel), ("charger", charger), ("accessibleBay", bay), ("onStreet", street)]
    return {"version": 1, "generated": "x",
            "places": [{"id": f"{k}-{i}", "kind": k} for k, n in kinds for i in range(n)]}


class Check(unittest.TestCase):
    def test_healthy_without_old(self):
        self.assertEqual(c.check(snap(), None), [])

    def test_car_park_floor(self):
        self.assertEqual(len(c.check(snap(car=2999), None)), 1)

    def test_fuel_floor(self):
        self.assertEqual(len(c.check(snap(fuel=799), None)), 1)

    def test_charger_floor(self):
        self.assertEqual(len(c.check(snap(charger=499), None)), 1)

    def test_accessible_bay_floor(self):
        self.assertEqual(len(c.check(snap(bay=399), None)), 1)

    def test_on_street_floor(self):
        self.assertEqual(len(c.check(snap(street=19), None)), 1)

    def test_dublin_loss_drop_25_percent(self):
        self.assertEqual(len(c.check(snap(bay=450), snap(bay=600))), 1)
        self.assertEqual(len(c.check(snap(street=30), snap(street=40))), 1)

    def test_fuel_drop_25_percent(self):
        self.assertEqual(len(c.check(snap(fuel=1000), snap(fuel=1334))), 1)

    def test_charger_drop_25_percent(self):
        self.assertEqual(len(c.check(snap(charger=800), snap(charger=1067))), 1)

    def test_car_park_drop_25_percent(self):
        self.assertEqual(len(c.check(snap(car=4000), snap(car=5334))), 1)

    def test_fuel_drop_10_percent(self):
        self.assertEqual(c.check(snap(fuel=900), snap(fuel=1000)), [])

    def test_missing_places(self):
        self.assertEqual(len(c.check({"version": 1, "generated": "x"}, None)), 1)

    def test_not_an_object(self):
        self.assertEqual(len(c.check([], None)), 1)

    def test_version_must_be_int(self):
        new = snap()
        new["version"] = "1"
        self.assertEqual(len(c.check(new, None)), 1)

    def test_generated_must_be_non_empty_string(self):
        for bad in ("", None, 5):
            new = snap()
            new["generated"] = bad
            self.assertEqual(len(c.check(new, None)), 1)

    def test_non_dict_places_ignored(self):
        new = snap()
        new["places"] += ["junk", 3, None]
        self.assertEqual(c.check(new, None), [])


if __name__ == "__main__":
    unittest.main()
