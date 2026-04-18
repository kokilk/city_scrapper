"""
PLUTO Lookup — NYC Property Owner from NYC Open Data (Free, no API key)

Uses the NYC Primary Land Use Tax Lot Output (PLUTO) dataset to get:
  - Property owner name
  - Building class + year built
  - Assessed value

Only runs for NYC addresses. Gracefully skips for other cities.

Dataset: https://data.cityofnewyork.us/resource/64uk-42ks.json
Socrata API — no authentication required for basic queries.

Input:  .tmp/normalized_address.json
Output: .tmp/pluto_owner.json
  {
    "owner_name": "...",
    "bldg_class": "...",
    "year_built": 0,
    "assessed_total": 0.0,
    "lot_area": 0,
    "num_floors": 0.0,
    "borough": "...",
    "block": "...",
    "lot": "...",
    "source": "NYC_PLUTO"
  }
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent
TMP = BASE / ".tmp"
INPUT_PATH = TMP / "normalized_address.json"
OUTPUT_PATH = TMP / "pluto_owner.json"

PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"

BOROUGH_CODE_MAP = {
    "MANHATTAN": "MN",
    "NEW YORK": "MN",
    "BROOKLYN": "BK",
    "QUEENS": "QN",
    "BRONX": "BX",
    "STATEN ISLAND": "SI",
}


def _fetch_url(url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        print(f"[pluto_lookup] HTTP error: {exc}", file=sys.stderr)
        return []


def _is_nyc(addr: dict) -> bool:
    city = addr.get("city", "").upper()
    nyc_cities = {
        "NEW YORK", "MANHATTAN", "BROOKLYN", "QUEENS",
        "BRONX", "STATEN ISLAND", "NEW YORK CITY",
    }
    return city in nyc_cities


def _parse_house_number(delivery_line: str) -> str:
    parts = delivery_line.strip().split()
    return parts[0] if parts and (parts[0].isdigit() or parts[0][:-1].isdigit()) else ""


def _normalize_street_for_pluto(delivery_line: str) -> str:
    """Extract just the street name portion, strip unit info."""
    parts = delivery_line.strip().upper().split()
    if parts and (parts[0].isdigit() or (len(parts[0]) > 1 and parts[0][:-1].isdigit())):
        parts = parts[1:]
    # Strip unit suffixes
    for suffix in ["STE", "APT", "UNIT", "FL", "FLOOR", "#"]:
        if suffix in parts:
            idx = parts.index(suffix)
            parts = parts[:idx]
    return " ".join(parts)


def lookup_owner(addr: dict) -> dict:
    if not _is_nyc(addr):
        print("[pluto_lookup] Not an NYC address — skipping PLUTO lookup")
        return {}

    delivery = addr.get("delivery_line_1", "")
    city = addr.get("city", "MANHATTAN").upper()
    borough_code = BOROUGH_CODE_MAP.get(city, "MN")
    house = _parse_house_number(delivery)
    street = _normalize_street_for_pluto(delivery)

    print(f"[pluto_lookup] Looking up: house={house} street={street} borough={borough_code}")

    params = urllib.parse.urlencode({
        "$where": (
            f"upper(address) like '%{street}%' "
            f"AND borough = '{borough_code}'"
        ),
        "$limit": "10",
    })
    url = f"{PLUTO_URL}?{params}"
    results = _fetch_url(url)

    # Try to match house number
    if house and results:
        matched = [
            r for r in results
            if r.get("address", "").strip().startswith(house)
        ]
        if matched:
            results = matched

    if not results:
        print("[pluto_lookup] No PLUTO record found for this address")
        return {}

    r = results[0]
    owner = {
        "owner_name": r.get("ownername", ""),
        "bldg_class": r.get("bldgclass", ""),
        "year_built": _safe_int(r.get("yearbuilt")),
        "assessed_total": _safe_float(r.get("assesstot")),
        "lot_area": _safe_int(r.get("lotarea")),
        "num_floors": _safe_float(r.get("numfloors")),
        "borough": r.get("borough", ""),
        "block": r.get("block", ""),
        "lot": r.get("lot", ""),
        "source": "NYC_PLUTO",
    }
    print(f"[pluto_lookup] Owner found: {owner['owner_name']}")
    return owner


def _safe_int(val: object) -> int | None:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_float(val: object) -> float | None:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[pluto_lookup] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    addr = json.loads(INPUT_PATH.read_text())
    owner = lookup_owner(addr)

    OUTPUT_PATH.write_text(json.dumps(owner, indent=2, default=str))
    if owner:
        print(f"[pluto_lookup] ✓ Owner data → {OUTPUT_PATH}")
    else:
        print(f"[pluto_lookup] Empty result → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
