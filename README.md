# ParkGlas website and map data

This repository publishes two things for the ParkGlas iPhone app:

- **The website:** the landing, support and privacy pages in `web/`.
- **The map data:** `snapshot.json`, a list of car parks, fuel stations and EV chargers in the Republic of Ireland,
  rebuilt every week by `.github/workflows/snapshot.yml` from open data.

The app's own source code is not in this repository.

## How the data is built

`Tools/build_snapshot.py` reads OpenStreetMap (through the Overpass API) and open data from Dublin City Council and
Cork City Council, and writes one JSON file. `Tools/check_snapshot.py` refuses to publish a file that is much
smaller than the last one. Both use only the Python standard library.

```bash
python3 Tools/build_snapshot.py --out snapshot.json
```

```bash
python3 -m unittest discover -s Tools -p "test_*.py"
```

## Data sources and licences

Map data © OpenStreetMap contributors, under the Open Database Licence. Contains data from Dublin City Council and
Cork City Council, under CC BY 4.0. ParkGlas is not affiliated with any car park operator.
