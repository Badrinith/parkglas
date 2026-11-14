import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import build_snapshot as b


def car_park(tags, **extra):
    return {"type": "node", "id": 1, "lat": 53.0, "lon": -6.0,
            "tags": {"amenity": "parking", **tags}, **extra}


class OsmToPlace(unittest.TestCase):
    def test_private_dropped(self):
        self.assertIsNone(b.osm_to_place(car_park({"access": "private"})))
        self.assertIsNone(b.osm_to_place(car_park({"access": "no"})))

    def test_way_uses_center(self):
        el = {"type": "way", "id": 7, "center": {"lat": 53.1234567891, "lon": -6.5},
              "tags": {"amenity": "parking", "name": "Quay St"}}
        p = b.osm_to_place(el)
        self.assertEqual(p["id"], "osm-w7")
        self.assertEqual((p["lat"], p["lon"]), (53.123457, -6.5))

    def test_missing_coordinates_dropped(self):
        self.assertIsNone(b.osm_to_place({"type": "way", "id": 1, "tags": {"amenity": "parking", "name": "X"}}))

    def test_fee(self):
        self.assertIs(b.osm_to_place(car_park({"fee": "yes"}))["fee"], True)
        self.assertIs(b.osm_to_place(car_park({"fee": "no"}))["fee"], False)
        self.assertNotIn("fee", b.osm_to_place(car_park({"fee": "interval"})))

    def test_capacity_non_numeric_omitted(self):
        self.assertNotIn("capacity", b.osm_to_place(car_park({"capacity": "about 40", "name": "X"})))
        self.assertEqual(b.osm_to_place(car_park({"capacity": "40"}))["capacity"], 40)

    def test_mapping(self):
        p = b.osm_to_place(car_park({"parking": "multi-storey", "capacity:disabled": "3",
                                     "capacity:charging": "2", "maxheight": "2.1", "name": "X"}))
        self.assertEqual(p["parkingType"], "multiStorey")
        self.assertEqual((p["accessibleSpaces"], p["ev"], p["maxHeight"], p["kind"]), (3, True, "2.1 m", "carPark"))
        self.assertEqual(b.osm_to_place(car_park({"parking": "street_side", "name": "X"})).get("parkingType"), None)

    def test_fuel_kind(self):
        el = {"type": "node", "id": 2, "lat": 53, "lon": -6, "tags": {"amenity": "fuel", "brand": "Circle K"}}
        p = b.osm_to_place(el)
        self.assertEqual((p["kind"], p["brand"]), ("fuel", "Circle K"))

    def test_no_none_values(self):
        p = b.osm_to_place(car_park({"name": "X"}))
        self.assertFalse([k for k, v in p.items() if v is None])


class PublicParking(unittest.TestCase):
    def kept(self, tags):
        return b.osm_to_place(car_park(tags)) is not None

    def test_non_public_access_dropped(self):
        for v in ("permit", "residents", "employees", "staff", "delivery", "destination",
                  "agricultural", "forestry", "military", "unknown"):
            with self.subTest(access=v):
                self.assertFalse(self.kept({"access": v, "name": "X"}))

    def test_public_access_kept(self):
        for v in ("yes", "public", "permissive"):
            with self.subTest(access=v):
                self.assertTrue(self.kept({"access": v}))

    def test_no_access_without_public_signal_dropped(self):
        self.assertFalse(self.kept({}))
        self.assertFalse(self.kept({"capacity": "8"}))
        self.assertFalse(self.kept({"parking": "surface"}))

    def test_no_access_with_public_signal_kept(self):
        for tags in ({"name": "Quay St"}, {"operator": "Council"}, {"fee": "no"}, {"fee": "interval"},
                     {"capacity": "25"}, {"parking": "multi-storey"}, {"parking": "underground"},
                     {"park_ride": "yes"}):
            with self.subTest(tags=tags):
                self.assertTrue(self.kept(tags))

    def test_capacity_threshold(self):
        self.assertTrue(self.kept({"capacity": "20"}))
        self.assertFalse(self.kept({"capacity": "19"}))

    def test_park_ride_no_is_not_a_signal(self):
        self.assertFalse(self.kept({"park_ride": "no"}))

    def test_informal_and_garage_dropped(self):
        self.assertFalse(self.kept({"informal": "yes", "access": "yes"}))
        self.assertFalse(self.kept({"parking": "garage", "access": "yes"}))
        self.assertFalse(self.kept({"parking": "garage", "name": "X"}))

    def test_fuel_and_charger_without_access_kept(self):
        fuel = {"type": "node", "id": 2, "lat": 53, "lon": -6, "tags": {"amenity": "fuel"}}
        charger = {"type": "node", "id": 9, "lat": 53, "lon": -6, "tags": {"amenity": "charging_station"}}
        self.assertIsNotNone(b.osm_to_place(fuel))
        self.assertIsNotNone(b.osm_to_place(charger))


class CustomerParking(unittest.TestCase):
    def place(self, tags):
        return b.osm_to_place(car_park(tags))

    def test_access_customers_kept(self):
        self.assertEqual(self.place({"access": "customers", "name": "Hotel"})["access"], "customers")

    def test_nameless_customers_dropped_operator_only_kept(self):
        self.assertIsNone(self.place({"access": "customers"}))
        self.assertIsNone(self.place({"access": "customers", "capacity": "50"}))
        p = self.place({"access": "customers", "operator": "Aldi Stores (Ireland) Limited"})
        self.assertEqual((p["access"], p["name"]), ("customers", "Aldi"))

    def test_display_operator(self):
        for raw, want in {"Aldi Stores (Ireland) Limited": "Aldi", "Tesco Ireland": "Tesco", "Lidl Ireland GmbH": "Lidl",
                          "Dunnes Stores": "Dunnes", "SuperValu": "SuperValu", "Ltd": "Ltd", "Acme Co.": "Acme",
                          "Foo  Bar plc": "Foo Bar"}.items():
            with self.subTest(raw=raw):
                self.assertEqual(b.display_operator(raw), want)

    def test_retail_name_without_access(self):
        self.assertEqual(self.place({"name": "Lidl"})["access"], "customers")
        self.assertEqual(self.place({"name": "Liffey Valley Shopping Centre"})["access"], "customers")

    def test_operator_sets_name_when_unnamed(self):
        p = self.place({"operator": "Tesco Ireland"})
        self.assertEqual((p["access"], p["name"]), ("customers", "Tesco"))
        self.assertEqual(self.place({"access": "customers", "operator": "Aldi", "name": "Front"})["name"], "Front")

    def test_non_public_access_with_retail_name_dropped(self):
        self.assertIsNone(self.place({"access": "private", "name": "Tesco staff"}))
        self.assertIsNone(self.place({"access": "permit", "name": "Lidl"}))

    def test_public_access_with_retail_name_is_public(self):
        p = self.place({"access": "yes", "name": "Lidl"})
        self.assertNotIn("access", p)

    def test_short_brand_words_need_word_boundary(self):
        self.assertNotIn("access", self.place({"name": "Sparrow Lane car park"}))
        self.assertNotIn("access", self.place({"name": "Spare Street"}))
        self.assertEqual(self.place({"name": "SPAR Ballina"})["access"], "customers")
        self.assertEqual(self.place({"name": "B&Q Carrickmines"})["access"], "customers")

    def test_informal_and_garage_customer_dropped(self):
        self.assertIsNone(self.place({"access": "customers", "informal": "yes"}))
        self.assertIsNone(self.place({"access": "customers", "parking": "garage"}))

    def test_maxstay_text(self):
        cases = {"2 hours": "2 hours", "2 h": "2 hours", "2h": "2 hours", "120 minutes": "2 hours",
                 "90 min": "90 minutes", "1.5 hours": "1.5 hours", "30": "30 minutes", "1 hour": "1 hour",
                 "1h": "1 hour", "unlimited": None, "no": None, "until 6pm": "until 6pm", "x" * 40: None}
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(b.max_stay_text({"maxstay": raw}), want)
        self.assertIsNone(b.max_stay_text({}))

    def test_centra_needs_word_boundary(self):
        self.assertNotIn("access", self.place({"name": "Central Car Park"}))
        self.assertEqual(self.place({"name": "Centra Ballina"})["access"], "customers")

    def test_maxstay_without_digit_or_zero_omitted(self):
        for raw in ("yes", "Customer only", "inf hours", "Two hours", "0", "0 hours", "0.0 min"):
            with self.subTest(raw=raw):
                self.assertIsNone(b.max_stay_text({"maxstay": raw}))

    def test_maxstay_written_for_any_car_park(self):
        self.assertEqual(self.place({"access": "yes", "maxstay": "2 hours"})["maxStay"], "2 hours")
        self.assertEqual(self.place({"name": "Lidl", "maxstay": "90 min"})["maxStay"], "90 minutes")
        self.assertNotIn("maxStay", self.place({"name": "X", "maxstay": "no"}))


def charger(tags, **extra):
    return {"type": "node", "id": 9, "lat": 53.0, "lon": -6.0,
            "tags": {"amenity": "charging_station", **tags}, **extra}


class Operators(unittest.TestCase):
    def op(self, tags):
        return b.osm_to_place(car_park(tags)).get("operator")

    def test_known_operator_from_name(self):
        self.assertEqual(self.op({"name": "Q-Park Henry Street"}), "Q-Park")

    def test_known_operator_from_operator_tag(self):
        self.assertEqual(self.op({"name": "Car Park", "operator": "APCOA Parking Ireland Ltd"}), "APCOA")

    def test_known_operator_from_brand(self):
        self.assertEqual(self.op({"name": "Car Park", "brand": "Euro Car Parks"}), "Euro Car Parks")

    def test_other_operator_is_display_name(self):
        self.assertEqual(self.op({"name": "Car Park", "operator": "Cork City Council"}), "Cork City Council")

    def test_operator_equal_to_name_omitted(self):
        self.assertNotIn("operator", b.osm_to_place(car_park({"name": "Cork City Council", "operator": "Cork City Council"})))
        self.assertNotIn("operator", b.osm_to_place(car_park({"name": "Q-Park", "operator": "Q-Park"})))

    def test_no_operator_omitted(self):
        self.assertNotIn("operator", b.osm_to_place(car_park({"name": "Quay St"})))

    def test_operator_name_function(self):
        self.assertEqual(b.operator_name({"amenity": "parking", "name": "Luas Park and Ride"}), "Luas")
        self.assertIsNone(b.operator_name({"amenity": "fuel", "name": "Q-Park"}))

    def test_commercial_operator_kept_public_without_signals(self):
        p = b.osm_to_place(car_park({"operator": "Q-Park"}))
        self.assertIsNotNone(p)
        self.assertNotIn("access", p)

    def test_commercial_operator_not_customer_by_retail_word(self):
        p = b.osm_to_place(car_park({"name": "Q-Park Dundrum Shopping Centre"}))
        self.assertNotIn("access", p)
        self.assertEqual(p["operator"], "Q-Park")

    def test_non_commercial_operator_keeps_retail_rule(self):
        p = b.osm_to_place(car_park({"name": "Luas Tesco"}))
        self.assertEqual(p.get("access"), "customers")

    def test_private_commercial_still_dropped(self):
        self.assertIsNone(b.osm_to_place(car_park({"name": "X", "operator": "APCOA", "access": "private"})))

    def test_fuel_and_charger_unaffected(self):
        fuel = b.osm_to_place({"type": "node", "id": 2, "lat": 53, "lon": -6,
                               "tags": {"amenity": "fuel", "name": "Q-Park Fuel"}})
        chg = b.osm_to_place({"type": "node", "id": 3, "lat": 53, "lon": -6,
                              "tags": {"amenity": "charging_station", "operator": "APCOA"}})
        self.assertNotIn("operator", fuel)
        self.assertNotIn("operator", chg)


class Charger(unittest.TestCase):
    def test_maps_with_sorted_sockets_and_power(self):
        p = b.osm_to_place(charger({"socket:type2": "2", "socket:type2_combo": "1", "socket:chademo": "1",
                                    "socket:type2:output": "22 kW", "socket:type2_combo:output": "150 kW",
                                    "capacity": "4", "name": "Hub", "operator": "ESB"}))
        self.assertEqual((p["kind"], p["sockets"], p["maxKW"]), ("charger", ["ccs", "chademo", "type2"], 150))
        self.assertEqual((p["capacity"], p["name"], p["brand"]), (4, "Hub", "ESB"))

    def test_brand_beats_operator(self):
        p = b.osm_to_place(charger({"brand": "Tesla", "operator": "Tesla Inc"}))
        self.assertEqual(p["brand"], "Tesla")

    def test_no_means_not_a_socket(self):
        p = b.osm_to_place(charger({"socket:type2": "no", "socket:chademo": "0", "socket:tesla_destination": "1"}))
        self.assertEqual(p["sockets"], ["tesla"])
        self.assertNotIn("sockets", b.osm_to_place(charger({"socket:type2": "no"})))

    def test_type2_cable(self):
        self.assertEqual(b.osm_to_place(charger({"socket:type2_cable": "1"}))["sockets"], ["type2"])

    def test_power_parsing(self):
        self.assertEqual(b.osm_to_place(charger({"charging_station:output": "50 kW"}))["maxKW"], 50)
        self.assertEqual(b.osm_to_place(charger({"socket:type2:output": "22kW"}))["maxKW"], 22)
        self.assertEqual(b.osm_to_place(charger({"socket:type2:output": "7.4"}))["maxKW"], 7.4)
        self.assertNotIn("maxKW", b.osm_to_place(charger({"socket:type2:output": "fast"})))
        self.assertNotIn("maxKW", b.osm_to_place(charger({"socket:type2:output": "500 kW"})))

    def test_private_dropped(self):
        self.assertIsNone(b.osm_to_place(charger({"access": "private"})))

    def test_not_deduplicated_against_cork(self):
        cork = [{"latitude": 53.0, "longitude": -6.0}]
        snap = b.build([charger({})], cork, [], [], 1)
        self.assertEqual([p["kind"] for p in snap["places"]], ["charger"])


class Dedup(unittest.TestCase):
    def test_near_any(self):
        cork = [(51.9000, -8.4700)]
        self.assertTrue(b.near_any(51.9000 + 50 / 111_000, -8.4700, cork))
        self.assertFalse(b.near_any(51.9000 + 500 / 111_000, -8.4700, cork))

    def test_build_drops_near_cork_only_for_car_parks(self):
        near = {"type": "node", "id": 1, "lat": 51.90045, "lon": -8.47, "tags": {"amenity": "parking", "name": "X"}}
        far = {"type": "node", "id": 2, "lat": 51.9045, "lon": -8.47, "tags": {"amenity": "parking", "name": "X"}}
        fuel = {"type": "node", "id": 3, "lat": 51.90045, "lon": -8.47, "tags": {"amenity": "fuel"}}
        cork = [{"latitude": 51.9, "longitude": -8.47}]
        snap = b.build([near, far, fuel], cork, [], [], 5)
        self.assertEqual(sorted(p["id"] for p in snap["places"]), ["osm-n2", "osm-n3"])
        self.assertEqual(snap["version"], 5)


class Dublin(unittest.TestCase):
    def feat(self, **props):
        return {"geometry": {"type": "Point", "coordinates": [-6.27, 53.31]},
                "properties": {"Location": "Rathgar Avenue", "Zone": "Orange", "Tariff": "2.4",
                               "No_Spaces": "45 P&D / DP (Total)", **props}}

    def test_pd(self):
        p = b.dublin_pd_to_place(self.feat(), 3)
        self.assertEqual((p["id"], p["kind"], p["capacity"], p["charge"], p["zone"], p["priceMayBeStale"]),
                         ("dcc-pd-3", "onStreet", 45, "€2.40 per hour", "Orange", True))

    def test_pd_projected_coords_skipped(self):
        f = self.feat()
        f["geometry"]["coordinates"] = [315763.7, 234926.4]
        self.assertIsNone(b.dublin_pd_to_place(f, 1))

    def test_ab_default_one(self):
        f = {"geometry": {"type": "Point", "coordinates": [-6.25, 53.34]},
             "properties": {"Street Name": "ABBEY STREET LOWER"}}
        p = b.dublin_ab_to_place(f, 9)
        self.assertEqual((p["id"], p["kind"], p["accessibleSpaces"]), ("dcc-ab-9", "accessibleBay", 1))


class CleanText(unittest.TestCase):
    def test_maxheight(self):
        for raw, want in (("2.1", "2.1 m"), ("2", "2 m"), ("2.1 m", "2.1 m"), ("2.10m", "2.1 m"),
                          ("7'", "2.1 m"), ("7 ft", "2.1 m"), ("7'6\"", "2.3 m"), ("6'9\"", "2.1 m")):
            self.assertEqual(b.max_height_text(raw), want, raw)
        for raw in ("default", "none", "no", "unsigned", "", "tall", "2.1;3"):
            self.assertIsNone(b.max_height_text(raw), raw)

    def test_maxheight_reaches_place(self):
        self.assertEqual(b.osm_to_place(car_park({"maxheight": "2.1", "name": "X"}))["maxHeight"], "2.1 m")
        self.assertNotIn("maxHeight", b.osm_to_place(car_park({"maxheight": "default", "name": "X"})))

    def test_charge(self):
        self.assertEqual(b.charge_text("2 EUR/hour"), "€2/hour")
        self.assertEqual(b.charge_text("EUR 1.50"), "€1.50")
        self.assertEqual(b.charge_text("€2 per hour"), "€2 per hour")
        self.assertIsNone(b.charge_text("x" * 41))
        self.assertIsNone(b.charge_text("2 EUR @ weekends"))
        self.assertIsNone(b.charge_text("2 EUR; 3 EUR"))
        self.assertIsNone(b.charge_text(""))

    def test_charge_reaches_place(self):
        self.assertEqual(b.osm_to_place(car_park({"charge": "2 EUR/hour", "name": "X"}))["charge"], "€2/hour")
        self.assertNotIn("charge", b.osm_to_place(car_park({"charge": "a;b", "name": "X"})))


CORK = {"identifier": 7, "name": "Paul Street", "spaces": "430", "free_spaces": 12, "latitude": "51.9006",
        "longitude": -8.4731, "price": "€2.50 per hour", "opening_times": "24 hours", "height_restrictions": "1.9m"}


class CorkPlaces(unittest.TestCase):
    def test_mapping_matches_the_app(self):
        p = b.cork_to_place(CORK)
        self.assertEqual((p["id"], p["kind"], p["name"], p["parkingType"], p["fee"], p["charge"], p["capacity"]),
                         ("cork-7", "carPark", "Paul Street", "multiStorey", True, "€2.50 per hour", 430))
        self.assertEqual((p["hoursText"], p["maxHeight"], p["lat"], p["lon"]), ("24 hours", "1.9m", 51.9006, -8.4731))

    def test_park_and_ride_is_surface(self):
        self.assertEqual(b.cork_to_place({**CORK, "name": "Black Ash Park & Ride"})["parkingType"], "surface")

    def test_unusable_records_skipped(self):
        self.assertIsNone(b.cork_to_place({**CORK, "identifier": None}))
        self.assertIsNone(b.cork_to_place({**CORK, "latitude": None}))

    def test_build_emits_cork_places_and_dedups_osm(self):
        near = {"type": "node", "id": 1, "lat": 51.9006, "lon": -8.4731, "tags": {"amenity": "parking", "name": "X"}}
        snap = b.build([near], [CORK], [], [], 1)
        self.assertEqual([p["id"] for p in snap["places"]], ["cork-7"])

    def test_no_feed_no_cork_places(self):
        self.assertEqual(b.build([], [], [], [], 1)["places"], [])


class Strict(unittest.TestCase):
    def test_decision(self):
        self.assertEqual(b.strict_problems([CORK], [1], [1]), [])
        self.assertEqual(len(b.strict_problems([], [1], [1])), 1)
        self.assertEqual(len(b.strict_problems([CORK], [], [1])), 1)
        self.assertEqual(len(b.strict_problems([CORK], [1], [])), 1)
        self.assertEqual(len(b.strict_problems([], [], [])), 3)


class Overpass(unittest.TestCase):
    def test_remark_means_truncated(self):
        self.assertTrue(b.overpass_truncated({"elements": [], "remark": "runtime error: Query timed out"}))
        self.assertFalse(b.overpass_truncated({"elements": []}))


class Republic(unittest.TestCase):
    def test_towns(self):
        no = {"Belfast": (54.5973, -5.9301), "Derry": (54.9966, -7.3086), "Enniskillen": (54.3438, -7.6315),
              "Newry": (54.1751, -6.3402), "Strabane": (54.8274, -7.4633), "Belleek": (54.4790, -8.0900),
              "Warrenpoint": (54.1010, -6.2530)}
        yes = {"Letterkenny": (54.9504, -7.7342), "Lifford": (54.8386, -7.4700), "Dundalk": (54.0010, -6.4044),
               "Monaghan": (54.2492, -6.9683), "Malin Head": (55.381, -7.374), "Dublin": (53.3498, -6.2603),
               "Cork": (51.8985, -8.4756), "Galway": (53.2707, -9.0568), "Clones": (54.1790, -7.2317),
               "Ballyshannon": (54.5010, -8.1900), "Carlingford": (54.0430, -6.1880), "Carrickdale": (54.0991, -6.3601)}
        for n, (la, lo) in no.items():
            self.assertFalse(b.in_republic(la, lo), n)
        for n, (la, lo) in yes.items():
            self.assertTrue(b.in_republic(la, lo), n)

    def test_build_filters_northern_ireland(self):
        belfast = {"type": "node", "id": 9, "lat": 54.5973, "lon": -5.9301, "tags": {"amenity": "fuel"}}
        dublin = {"type": "node", "id": 10, "lat": 53.35, "lon": -6.26, "tags": {"amenity": "fuel"}}
        snap = b.build([belfast, dublin], [], [], [], 1)
        self.assertEqual([p["id"] for p in snap["places"]], ["osm-n10"])
        self.assertEqual(snap["removed_outside_republic"], 1)


if __name__ == "__main__":
    unittest.main()
