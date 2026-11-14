#!/usr/bin/env python3
"""Gate for the weekly refresh: exits non-zero when a new snapshot must not be published.

Usage: python3 Tools/check_snapshot.py NEW.json [OLD.json]
A missing or unreadable OLD file means only the absolute floors apply.
"""
import json
import sys

FLOORS = {"carPark": 3000, "fuel": 800, "charger": 500, "accessibleBay": 400, "onStreet": 20}
MAX_DROP = 0.20


def _counts(snapshot):
    counts = dict.fromkeys(FLOORS, 0)
    for p in snapshot["places"]:
        if isinstance(p, dict) and p.get("kind") in counts:
            counts[p["kind"]] += 1
    return counts


def check(new, old):
    """List of problems; empty means publish."""
    if not isinstance(new, dict) or not isinstance(new.get("places"), list):
        return ["new snapshot has no places list"]
    problems = []
    if type(new.get("version")) is not int:
        problems.append("version is missing or not an integer")
    if not isinstance(new.get("generated"), str) or not new["generated"]:
        problems.append("generated is missing or empty")
    counts = _counts(new)
    for kind, floor in FLOORS.items():
        if counts[kind] < floor:
            problems.append(f"{kind}: {counts[kind]} is below the minimum of {floor}")
    if isinstance(old, dict) and isinstance(old.get("places"), list):
        before = _counts(old)
        for kind in FLOORS:
            if before[kind] and counts[kind] < before[kind] * (1 - MAX_DROP):
                problems.append(f"{kind}: fell from {before[kind]} to {counts[kind]} (more than {MAX_DROP:.0%})")
    return problems


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    try:
        new = _load(sys.argv[1])
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read new snapshot: {e}")
    try:
        old = _load(sys.argv[2]) if len(sys.argv) == 3 else None
    except (OSError, ValueError):
        old = None  # nothing usable published yet
    found = check(new, old)
    for p in found:
        print("PROBLEM:", p)
    if not found:
        print("snapshot ok:", {k: v for k, v in _counts(new).items()})
    sys.exit(1 if found else 0)
