#!/usr/bin/env python3
"""Developer-time builder for App/Resources/snapshot.json (standard library only).

Usage: python3 Tools/build_snapshot.py --out App/Resources/snapshot.json
"""
import argparse
import json
import math
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = "ParkGlas-snapshot-builder/1.0"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
OVERPASS_QUERY = (
    '[out:json][timeout:180];area["ISO3166-1"="IE"][admin_level=2]->.a;'
    '(nwr["amenity"="parking"](area.a);nwr["amenity"="fuel"](area.a);nwr["amenity"="charging_station"](area.a););out center tags;'
)
CORK_URL = ("https://data.corkcity.ie/api/3/action/datastore_search"
            "?resource_id=f4677dac-bb30-412e-95a8-d3c22134e3c0&limit=100")
DCC_PD_PKG = "https://data.gov.ie/api/3/action/package_show?id=parking-meters-location-tariffs-and-zones-in-dublin-city"
DCC_AB_PKG = "https://data.smartdublin.ie/api/3/action/package_show?id=accessible-parking-spaces-dcc"
# python.org builds on macOS ship no CA bundle; fall back to the system one.
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)
IRELAND = (51.3, 55.5, -10.7, -5.9)  # lat min/max, lon min/max

PARKING_TYPES = {"multi-storey": "multiStorey", "underground": "underground", "surface": "surface"}


def _fetch(url, data=None, timeout=180, retries=1):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - any network failure triggers the retry
            last = e
    raise last


def _json(url, **kw):
    raw = _fetch(url, **kw)
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:  # some DCC files are Windows-1252
        return json.loads(raw.decode("cp1252"))


def _int(s):
    s = str(s).strip() if s is not None else ""
    return int(s) if s.isdigit() else None


# Northern Ireland boundary as (lat, lon) vertices (about 150 m accuracy), the OSM administrative boundary simplified
# to 470 points, so border towns and services land on the right side. Keep in step with HomeCities.niBorder in
# ParkGlasKit/Sources/ParkGlasKit/HomeCities.swift.
NI_BORDER = [
    (54.465, -8.178), (54.451, -8.143), (54.444, -8.150), (54.442, -8.162), (54.397, -8.084), (54.373, -8.064),
    (54.369, -8.056), (54.366, -8.057), (54.363, -8.039), (54.357, -8.031), (54.361, -8.008), (54.358, -8.001),
    (54.356, -7.998), (54.347, -7.999), (54.344, -7.986), (54.336, -7.983), (54.321, -7.964), (54.312, -7.962),
    (54.304, -7.946), (54.303, -7.919), (54.296, -7.911), (54.301, -7.902), (54.301, -7.888), (54.292, -7.881),
    (54.293, -7.862), (54.289, -7.865), (54.288, -7.871), (54.279, -7.873), (54.266, -7.873), (54.260, -7.860),
    (54.230, -7.860), (54.223, -7.855), (54.217, -7.860), (54.201, -7.812), (54.207, -7.804), (54.209, -7.768),
    (54.209, -7.749), (54.204, -7.739), (54.203, -7.711), (54.208, -7.702), (54.204, -7.692), (54.208, -7.685),
    (54.199, -7.689), (54.198, -7.684), (54.193, -7.685), (54.192, -7.679), (54.182, -7.677), (54.181, -7.672),
    (54.188, -7.664), (54.186, -7.656), (54.176, -7.646), (54.169, -7.629), (54.153, -7.625), (54.144, -7.610),
    (54.140, -7.592), (54.142, -7.575), (54.134, -7.575), (54.133, -7.569), (54.127, -7.566), (54.127, -7.556),
    (54.122, -7.547), (54.129, -7.547), (54.127, -7.538), (54.136, -7.528), (54.130, -7.520), (54.122, -7.479),
    (54.127, -7.472), (54.133, -7.472), (54.134, -7.467), (54.141, -7.468), (54.145, -7.453), (54.154, -7.442),
    (54.152, -7.431), (54.156, -7.410), (54.149, -7.412), (54.141, -7.425), (54.137, -7.421), (54.141, -7.401),
    (54.137, -7.391), (54.141, -7.384), (54.140, -7.373), (54.126, -7.393), (54.120, -7.392), (54.132, -7.363),
    (54.123, -7.346), (54.116, -7.346), (54.117, -7.336), (54.125, -7.327), (54.113, -7.319), (54.117, -7.308),
    (54.123, -7.305), (54.127, -7.316), (54.132, -7.312), (54.138, -7.319), (54.135, -7.328), (54.147, -7.340),
    (54.152, -7.326), (54.167, -7.310), (54.166, -7.300), (54.172, -7.291), (54.168, -7.280), (54.158, -7.286),
    (54.154, -7.284), (54.149, -7.290), (54.149, -7.299), (54.144, -7.301), (54.140, -7.284), (54.136, -7.286),
    (54.131, -7.293), (54.134, -7.299), (54.132, -7.309), (54.121, -7.298), (54.123, -7.279), (54.129, -7.278),
    (54.137, -7.263), (54.145, -7.264), (54.148, -7.257), (54.154, -7.258), (54.156, -7.253), (54.165, -7.258),
    (54.170, -7.240), (54.177, -7.258), (54.190, -7.256), (54.192, -7.259), (54.193, -7.236), (54.198, -7.233),
    (54.201, -7.243), (54.198, -7.249), (54.204, -7.248), (54.206, -7.232), (54.211, -7.232), (54.216, -7.221),
    (54.213, -7.209), (54.216, -7.199), (54.225, -7.188), (54.225, -7.184), (54.220, -7.185), (54.218, -7.171),
    (54.225, -7.145), (54.233, -7.150), (54.240, -7.146), (54.244, -7.159), (54.252, -7.143), (54.256, -7.142),
    (54.258, -7.151), (54.267, -7.152), (54.269, -7.159), (54.274, -7.161), (54.273, -7.179), (54.277, -7.179),
    (54.284, -7.171), (54.286, -7.173), (54.294, -7.207), (54.300, -7.212), (54.311, -7.198), (54.310, -7.179),
    (54.332, -7.180), (54.338, -7.189), (54.340, -7.182), (54.335, -7.153), (54.345, -7.128), (54.351, -7.124),
    (54.356, -7.104), (54.361, -7.102), (54.368, -7.110), (54.379, -7.084), (54.389, -7.071), (54.395, -7.070),
    (54.408, -7.056), (54.411, -7.057), (54.418, -7.040), (54.421, -7.029), (54.414, -7.016), (54.417, -7.013),
    (54.413, -7.001), (54.410, -6.999), (54.408, -7.002), (54.405, -6.996), (54.409, -6.982), (54.400, -6.976),
    (54.398, -6.959), (54.392, -6.960), (54.391, -6.944), (54.387, -6.946), (54.383, -6.938), (54.383, -6.924),
    (54.380, -6.933), (54.376, -6.931), (54.379, -6.922), (54.375, -6.911), (54.372, -6.912), (54.369, -6.907),
    (54.365, -6.911), (54.361, -6.903), (54.350, -6.906), (54.351, -6.893), (54.346, -6.886), (54.346, -6.876),
    (54.339, -6.876), (54.330, -6.864), (54.315, -6.863), (54.314, -6.856), (54.304, -6.859), (54.297, -6.851),
    (54.292, -6.851), (54.289, -6.860), (54.282, -6.859), (54.282, -6.868), (54.288, -6.872), (54.285, -6.878),
    (54.282, -6.875), (54.279, -6.878), (54.275, -6.865), (54.270, -6.866), (54.269, -6.853), (54.265, -6.852),
    (54.268, -6.839), (54.261, -6.828), (54.247, -6.829), (54.239, -6.819), (54.223, -6.816), (54.225, -6.809),
    (54.221, -6.800), (54.213, -6.801), (54.199, -6.776), (54.199, -6.756), (54.182, -6.741), (54.186, -6.735),
    (54.182, -6.721), (54.187, -6.721), (54.191, -6.713), (54.198, -6.710), (54.200, -6.692), (54.193, -6.683),
    (54.196, -6.678), (54.193, -6.665), (54.185, -6.659), (54.180, -6.644), (54.171, -6.636), (54.154, -6.630),
    (54.147, -6.632), (54.142, -6.641), (54.132, -6.640), (54.130, -6.650), (54.122, -6.649), (54.123, -6.661),
    (54.096, -6.645), (54.093, -6.652), (54.096, -6.659), (54.093, -6.662), (54.087, -6.656), (54.076, -6.658),
    (54.073, -6.669), (54.063, -6.661), (54.059, -6.647), (54.047, -6.640), (54.036, -6.624), (54.043, -6.616),
    (54.040, -6.607), (54.045, -6.605), (54.045, -6.595), (54.052, -6.596), (54.058, -6.587), (54.049, -6.558),
    (54.060, -6.532), (54.053, -6.511), (54.057, -6.510), (54.059, -6.497), (54.067, -6.485), (54.066, -6.471),
    (54.072, -6.481), (54.077, -6.478), (54.071, -6.462), (54.073, -6.456), (54.056, -6.443), (54.063, -6.412),
    (54.059, -6.391), (54.068, -6.383), (54.073, -6.364), (54.094, -6.366), (54.097, -6.362), (54.102, -6.367),
    (54.114, -6.366), (54.112, -6.340), (54.105, -6.334), (54.095, -6.336), (54.091, -6.318), (54.107, -6.309),
    (54.112, -6.285), (54.096, -6.259), (54.033, -6.113), (53.932, -5.951), (53.870, -5.826), (53.879, -5.816),
    (53.916, -5.732), (53.966, -5.650), (53.997, -5.610), (54.031, -5.579), (54.052, -5.490), (54.091, -5.399),
    (54.113, -5.358), (54.174, -5.268), (54.242, -5.193), (54.318, -5.137), (54.348, -5.123), (54.378, -5.116),
    (54.408, -5.101), (54.456, -5.087), (54.465, -5.078), (54.566, -5.182), (54.606, -5.212), (54.663, -5.245),
    (54.678, -5.244), (54.701, -5.249), (54.714, -5.260), (54.750, -5.295), (54.777, -5.328), (54.856, -5.436),
    (54.886, -5.453), (54.905, -5.457), (54.933, -5.477), (54.981, -5.519), (55.023, -5.571), (55.047, -5.614),
    (55.067, -5.664), (55.088, -5.740), (55.139, -5.812), (55.183, -5.848), (55.211, -5.881), (55.256, -5.944),
    (55.286, -6.009), (55.327, -6.044), (55.349, -6.075), (55.367, -6.110), (55.402, -6.222), (55.416, -6.289),
    (55.428, -6.400), (55.430, -6.500), (55.444, -6.579), (55.415, -6.744), (55.280, -6.719), (55.216, -6.822),
    (55.205, -6.942), (55.195, -6.978), (55.180, -6.989), (55.148, -7.054), (55.111, -7.153), (55.078, -7.222),
    (55.067, -7.253), (55.066, -7.267), (55.048, -7.286), (55.056, -7.299), (55.045, -7.318), (55.051, -7.345),
    (55.022, -7.391), (55.003, -7.406), (54.998, -7.391), (54.983, -7.407), (54.972, -7.400), (54.964, -7.407),
    (54.960, -7.402), (54.954, -7.406), (54.945, -7.392), (54.943, -7.425), (54.935, -7.447), (54.911, -7.445),
    (54.898, -7.453), (54.879, -7.442), (54.869, -7.444), (54.860, -7.455), (54.854, -7.456), (54.854, -7.461),
    (54.835, -7.471), (54.831, -7.481), (54.824, -7.484), (54.808, -7.517), (54.808, -7.528), (54.803, -7.528),
    (54.801, -7.539), (54.789, -7.549), (54.782, -7.543), (54.772, -7.548), (54.756, -7.548), (54.747, -7.535),
    (54.740, -7.549), (54.745, -7.558), (54.742, -7.579), (54.749, -7.575), (54.750, -7.579), (54.750, -7.587),
    (54.744, -7.589), (54.743, -7.617), (54.752, -7.637), (54.731, -7.677), (54.726, -7.698), (54.724, -7.697),
    (54.726, -7.712), (54.717, -7.736), (54.705, -7.745), (54.704, -7.750), (54.710, -7.778), (54.716, -7.779),
    (54.720, -7.789), (54.719, -7.805), (54.729, -7.817), (54.734, -7.818), (54.736, -7.837), (54.727, -7.855),
    (54.703, -7.880), (54.703, -7.918), (54.696, -7.921), (54.689, -7.907), (54.691, -7.899), (54.685, -7.898),
    (54.675, -7.914), (54.663, -7.904), (54.656, -7.892), (54.651, -7.857), (54.643, -7.854), (54.639, -7.857),
    (54.636, -7.851), (54.633, -7.854), (54.631, -7.852), (54.633, -7.828), (54.644, -7.814), (54.635, -7.805),
    (54.633, -7.783), (54.621, -7.772), (54.625, -7.758), (54.618, -7.754), (54.618, -7.742), (54.623, -7.738),
    (54.629, -7.716), (54.635, -7.709), (54.627, -7.703), (54.620, -7.706), (54.619, -7.693), (54.610, -7.697),
    (54.599, -7.752), (54.594, -7.760), (54.590, -7.763), (54.587, -7.759), (54.586, -7.762), (54.580, -7.787),
    (54.582, -7.793), (54.577, -7.799), (54.572, -7.797), (54.563, -7.818), (54.552, -7.833), (54.544, -7.824),
    (54.533, -7.851), (54.537, -7.858), (54.537, -7.906), (54.534, -7.950), (54.547, -7.970), (54.543, -7.991),
    (54.546, -8.006), (54.536, -8.014), (54.534, -8.012), (54.506, -8.042), (54.503, -8.038), (54.488, -8.043),
    (54.487, -8.088), (54.484, -8.099), (54.477, -8.091), (54.476, -8.113), (54.470, -8.112), (54.469, -8.115),
    (54.469, -8.165), (54.465, -8.177),
]


def _in_polygon(lat, lon, poly):
    inside = False
    for i, (la1, lo1) in enumerate(poly):
        la2, lo2 = poly[(i + 1) % len(poly)]
        if (lo1 > lon) != (lo2 > lon) and lat < (la2 - la1) * (lon - lo1) / (lo2 - lo1) + la1:
            inside = not inside
    return inside


def in_republic(lat, lon):
    return _in_ireland(lat, lon) and not _in_polygon(lat, lon, NI_BORDER)


def _in_ireland(lat, lon):
    return IRELAND[0] <= lat <= IRELAND[1] and IRELAND[2] <= lon <= IRELAND[3]


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


SOCKET_TAGS = {
    "type2": ("socket:type2", "socket:type2_cable"),
    "ccs": ("socket:type2_combo",),
    "chademo": ("socket:chademo",),
    "tesla": ("socket:tesla_supercharger", "socket:tesla_destination", "socket:tesla_supercharger_ccs"),
}


def _charger_fields(tags):
    sockets = sorted(k for k, names in SOCKET_TAGS.items()
                     if any(tags.get(n) not in (None, "", "no", "0") for n in names))
    kw = [float(m) for k, v in tags.items()
          if (k == "charging_station:output" or (k.startswith("socket:") and k.endswith(":output")))
          for m in re.findall(r"\d+(?:\.\d+)?", v)[:1]]
    kw = [x for x in kw if x <= 400]  # larger values are tagging mistakes (watts, totals)
    top = max(kw) if kw else None
    return {"sockets": sockets or None, "maxKW": int(top) if top is not None and top.is_integer() else top}


PUBLIC_ACCESS = {"yes", "public", "permissive"}
NON_PUBLIC_PARKING = {"garage", "garages", "garage_boxes", "carport", "carports", "driveway", "depot", "layby"}


RETAIL_WORDS = ("lidl", "aldi", "tesco", "dunnes", "supervalu", "centra", "spar", "ikea", "woodie", "b&q", "homebase",
                "shopping centre", "shopping center", "retail park", "supermarket", "outlet")
SHORT_RETAIL = {"spar", "aldi", "lidl", "ikea", "b&q", "centra"}  # whole words only, so "Sparrow" does not match
_RETAIL_RE = re.compile("|".join(
    (r"(?<![\w&])" + re.escape(w) + r"(?![\w&])") if w in SHORT_RETAIL else re.escape(w) for w in RETAIL_WORDS))


def _retail(tags):
    return bool(_RETAIL_RE.search(f"{tags.get('name', '')} | {tags.get('operator', '')}".lower()))


_LEGAL_TAIL = re.compile(
    r"[\s,]*(?:\(ireland\)|ireland|limited|ltd\.?|plc|stores|supermarkets|company|co\.|group|gmbh|uc|dac|teoranta|teo)$",
    re.IGNORECASE)


def display_operator(op):
    """An operator string for display: legal forms and filler stripped from the end; never empty."""
    out = " ".join(op.split())
    while (cut := _LEGAL_TAIL.sub("", out)) != out:
        out = cut
    return " ".join(out.split()) or op


KNOWN_OPERATORS = [  # (canonical name, regex on lower-cased "name | operator | brand")
    ("Q-Park", r"\bq[- ]?park\b"), ("APCOA", r"\bapcoa\b"), ("Euro Car Parks", r"\beuro ?car ?parks?\b"),
    ("Park Rite", r"\bpark ?rite\b"), ("NCPS", r"\bncps\b|national controlled parking"),
    ("Best Car Parks", r"\bbest car parks?\b"),
    ("Irish Rail", r"\birish rail\b|iarnr[oó]d [eé]ireann"), ("Luas", r"\bluas\b"),
    ("Dublin Airport", r"\bdublin airport\b|\bdaa\b"), ("Bus Éireann", r"\bbus [eé]ireann\b"),
]
COMMERCIAL_OPERATORS = {n for n, _ in KNOWN_OPERATORS[:6]}  # keep in step with Operators.commercial in the kit


def operator_name(tags):
    """Canonical operator for a known one, else the tidied `operator` tag, else None. Car parks only."""
    if tags.get("amenity") != "parking":
        return None
    hay = f"{tags.get('name', '')} | {tags.get('operator', '')} | {tags.get('brand', '')}".lower()
    for canonical, pattern in KNOWN_OPERATORS:
        if re.search(pattern, hay):
            return canonical
    return display_operator(tags["operator"]) if tags.get("operator") else None


def parking_access(tags):
    """'public', 'customers', or None (drop). Untagged access is public only with a public signal."""
    if tags.get("informal") == "yes" or tags.get("parking") in NON_PUBLIC_PARKING:
        return None
    access = tags.get("access")
    if operator_name(tags) in COMMERCIAL_OPERATORS and (access is None or access in PUBLIC_ACCESS):
        return "public"
    if access in PUBLIC_ACCESS:
        return "public"
    if access == "customers":  # without a name or operator a driver cannot tell whose customers
        return "customers" if tags.get("name") or tags.get("operator") else None
    if access:
        return None
    if _retail(tags):
        return "customers"
    public = bool(
        tags.get("name") or tags.get("operator") or "fee" in tags
        or (_int(tags.get("capacity")) or 0) >= 20
        or tags.get("parking") in ("multi-storey", "underground")
        or tags.get("park_ride") not in (None, "", "no")
    )
    return "public" if public else None


def max_stay_text(tags):
    raw = (tags.get("maxstay") or "").strip()
    if not any(ch.isdigit() for ch in raw):  # "yes", "customer only", "unlimited", "no"
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?", raw.lower())
    if not m:
        return raw if len(raw) < 40 else None
    n = float(m.group(1))
    if n == 0:
        return None
    if m.group(2) is None or m.group(2).startswith("m"):
        if n >= 60 and n % 60 == 0:
            n, hours = n / 60, True
        else:
            hours = False
    else:
        hours = True
    unit = ("hour" if n == 1 else "hours") if hours else ("minute" if n == 1 else "minutes")
    return f"{n:g} {unit}"


def max_height_text(raw):
    """Driver-readable height limit ("2.1 m") or None. Feet and inches become metres; filler words are dropped."""
    raw = (raw or "").strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m)?", raw)
    if m:
        n = float(m.group(1))
        return f"{n:g} m" if n > 0 else None
    m = re.fullmatch(r"(\d+)\s*(?:'|ft|feet)\s*(?:(\d+)\s*(?:\"|in|inches)?)?", raw)
    if m:
        metres = (int(m.group(1)) * 12 + int(m.group(2) or 0)) * 0.0254
        return f"{metres:.1f} m" if metres > 0 else None
    return None


def charge_text(raw):
    """Tidy OSM charge text, or None when it is too long or messy to show a driver."""
    raw = " ".join((raw or "").split())
    if not raw or len(raw) > 40 or "@" in raw or ";" in raw:
        return None
    raw = re.sub(r"(\d(?:\.\d+)?)\s*EUR\b", r"€\1", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bEUR\s*(?=\d)", "€", raw, flags=re.IGNORECASE)
    return re.sub(r"\bEUR\b", "€", raw, flags=re.IGNORECASE)


def osm_to_place(el):
    tags = el.get("tags") or {}
    if tags.get("access") in ("private", "no"):
        return None
    access = parking_access(tags) if tags.get("amenity") == "parking" else None
    if tags.get("amenity") == "parking" and not access:
        return None
    c = el if "lat" in el else el.get("center") or {}
    if "lat" not in c or "lon" not in c:
        return None
    ptype = el.get("type", "node")
    if tags.get("amenity") == "charging_station":
        return _clean({
            "id": f"osm-{ptype[0]}{el['id']}",
            "kind": "charger",
            "name": tags.get("name"),
            "lat": round(c["lat"], 6),
            "lon": round(c["lon"], 6),
            "capacity": _int(tags.get("capacity")),
            "brand": tags.get("brand") or tags.get("operator"),
            **_charger_fields(tags),
        })
    charging = _int(tags.get("capacity:charging"))
    name = tags.get("name") or (display_operator(tags["operator"]) if access == "customers" and tags.get("operator") else None)
    op = operator_name(tags)
    return _clean({
        "id": f"osm-{ptype[0]}{el['id']}",
        "kind": "fuel" if tags.get("amenity") == "fuel" else "carPark",
        "name": name,
        "operator": op if op and op.lower() != (name or "").lower() else None,
        "lat": round(c["lat"], 6),
        "lon": round(c["lon"], 6),
        "parkingType": PARKING_TYPES.get(tags.get("parking")),
        "fee": {"yes": True, "no": False}.get(tags.get("fee")),
        "charge": charge_text(tags.get("charge")),
        "capacity": _int(tags.get("capacity")),
        "accessibleSpaces": _int(tags.get("capacity:disabled")),
        "openingHours": tags.get("opening_hours"),
        "maxHeight": max_height_text(tags.get("maxheight")),
        "ev": True if charging else None,
        "brand": tags.get("brand"),
        "access": "customers" if access == "customers" else None,
        "maxStay": max_stay_text(tags) if tags.get("amenity") == "parking" else None,
    })


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(min(1, math.sqrt(h)))


def near_any(lat, lon, points, metres=120):
    return any(_haversine(lat, lon, la, lo) <= metres for la, lo in points)


def _point(feature):
    """First WGS84 coordinate of the geometry, or None (e.g. Irish Grid values)."""
    g = feature.get("geometry") or {}
    c = g.get("coordinates")
    while c and isinstance(c[0], list):
        c = c[0]
    if not c or len(c) < 2:
        return None
    lon, lat = c[0], c[1]
    return (round(lat, 6), round(lon, 6)) if _in_ireland(lat, lon) else None


def _prop(props, *names):
    return next((props[n] for n in names if props.get(n) not in (None, "")), None)


def dublin_pd_to_place(feature, n):
    pt = _point(feature)
    if not pt:
        return None
    p = feature.get("properties") or {}
    tariff = re.search(r"\d+(?:\.\d+)?", str(_prop(p, "Tariff") or ""))
    spaces = re.search(r"\d+", str(_prop(p, "No_Spaces", "No Spaces") or ""))
    return _clean({
        "id": f"dcc-pd-{n}",
        "kind": "onStreet",
        "name": _prop(p, "Location"),
        "lat": pt[0],
        "lon": pt[1],
        "charge": f"€{float(tariff.group()):.2f} per hour" if tariff else None,
        "capacity": int(spaces.group()) if spaces else None,
        "hoursText": _prop(p, "Hours_of_Operation", "Hours of Operation"),
        "zone": _prop(p, "Zone"),
        "priceMayBeStale": True,
    })


def dublin_ab_to_place(feature, n):
    pt = _point(feature)
    if not pt:
        return None
    p = feature.get("properties") or {}
    street = _prop(p, "Street Name")
    count = _int(_prop(p, "No of Spaces", "Spaces", "Number of Spaces"))
    return _clean({
        "id": f"dcc-ab-{n}",
        "kind": "accessibleBay",
        "name": street.title() if street else None,
        "lat": pt[0],
        "lon": pt[1],
        "accessibleSpaces": count or 1,
    })


def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def cork_to_place(r):
    """A Cork feed record as a place; same mapping as CorkFeed.parse in the app, so a live record merges by id."""
    ident, lat, lon = _num(r.get("identifier")), _num(r.get("latitude")), _num(r.get("longitude"))
    if ident is None or lat is None or lon is None:
        return None
    name = r.get("name")
    return _clean({
        "id": f"cork-{int(ident)}",
        "kind": "carPark",
        "name": name,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "parkingType": "surface" if name and "Park & Ride" in name else "multiStorey",
        "fee": True,
        "charge": r.get("price") or None,
        "capacity": int(_num(r.get("spaces"))) if _num(r.get("spaces")) is not None else None,
        "hoursText": r.get("opening_times") or None,
        "maxHeight": r.get("height_restrictions") or None,
    })


def strict_problems(cork_records, dublin_pd, dublin_ab):
    """Reasons a --strict build must fail: a feed that returned nothing."""
    out = []
    if not cork_records:
        out.append("Cork feed returned no records")
    if not dublin_pd:
        out.append("Dublin pay-and-display dataset did not load")
    if not dublin_ab:
        out.append("Dublin accessible-bays dataset did not load")
    return out


def overpass_truncated(response):
    """A timed-out Overpass query still answers HTTP 200, with a `remark` and partial elements."""
    return isinstance(response, dict) and "remark" in response


def build(osm_elements, cork_records, dublin_pd_features, dublin_ab_rows, version):
    cork = [(_num(r.get("latitude")), _num(r.get("longitude"))) for r in cork_records
            if _num(r.get("latitude")) is not None and _num(r.get("longitude")) is not None]
    places = []
    for el in osm_elements:
        p = osm_to_place(el)
        if p and not (p["kind"] == "carPark" and near_any(p["lat"], p["lon"], cork)):
            places.append(p)
    places += [p for r in cork_records if (p := cork_to_place(r))]
    for conv, rows in ((dublin_pd_to_place, dublin_pd_features), (dublin_ab_to_place, dublin_ab_rows)):
        places += [p for n, f in enumerate(rows, 1) if (p := conv(f, n))]
    kept = [p for p in places if in_republic(p["lat"], p["lon"])]
    return {"version": version,
            "generated": datetime.fromtimestamp(version, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "places": kept,
            "removed_outside_republic": len(places) - len(kept)}


def fetch_overpass():
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    for url, tries in ((OVERPASS[0], 2), (OVERPASS[1], 1)):
        for _ in range(tries):
            try:
                resp = _json(url, data=body, retries=0)
                if overpass_truncated(resp):
                    raise ValueError(f"truncated result: {resp['remark']}")
                return resp["elements"]
            except Exception as e:  # noqa: BLE001
                print(f"warning: Overpass {url} failed: {e}", file=sys.stderr)
    raise SystemExit("Overpass failed on all attempts")


def _geojson_features(pkg_url, want):
    """Features from every GeoJSON resource of the package that `want(name)` accepts."""
    out = []
    for r in _json(pkg_url)["result"]["resources"]:
        if want(r.get("name", "")) and (r.get("format", "").lower() == "geojson" or r["url"].lower().endswith("geojson")):
            feats = _json(r["url"]).get("features", [])
            print(f"  {r['name']}: {len(feats)} features")
            out.append(feats)
    return out


def fetch_dublin(label, pkg_url, want, conv):
    try:
        batches = _geojson_features(pkg_url, want)
        feats = []
        for b in batches:  # a batch with no WGS84 coordinates (Irish Grid) is skipped, never guessed
            if any(_point(f) for f in b):
                feats += b
            else:
                print(f"warning: {label}: a dataset has non-WGS84 coordinates; skipped", file=sys.stderr)
        if not feats:
            raise ValueError("no usable features")
        return feats
    except Exception as e:  # noqa: BLE001
        print(f"warning: Dublin {label} unavailable ({e}); continuing without it", file=sys.stderr)
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when the Cork feed or a Dublin dataset is missing (used by the weekly job)")
    args = ap.parse_args()
    out = args.out
    osm = fetch_overpass()
    try:
        cork = _json(CORK_URL)["result"]["records"]
    except Exception as e:  # noqa: BLE001
        print(f"warning: Cork feed unavailable ({e}); no de-duplication", file=sys.stderr)
        cork = []
    pd = fetch_dublin("pay-and-display", DCC_PD_PKG, lambda n: "pay and display" in n.lower(), dublin_pd_to_place)
    ab = fetch_dublin("accessible bays", DCC_AB_PKG, lambda n: True, dublin_ab_to_place)
    if args.strict and (problems := strict_problems(cork, pd, ab)):
        sys.exit("strict build failed: " + "; ".join(problems))
    snap = build(osm, cork, pd, ab, int(time.time()))
    removed = snap.pop("removed_outside_republic")
    print(f"removed {removed} places outside the Republic")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"), ensure_ascii=False)
    counts = {}
    for p in snap["places"]:
        counts[p["kind"]] = counts.get(p["kind"], 0) + 1
    print(f"wrote {out}: {len(snap['places'])} places {counts}")


if __name__ == "__main__":
    main()
