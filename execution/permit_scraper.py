"""
Permit Scraper — Free public permit data by city

Replaces shovels_permit_fetch.py + shovels_contractor_fetch.py.
Uses free public APIs — no API key required.

Supported cities (auto-detected from normalized address):
  NYC   → NYC DOB Job Application Filings (data.cityofnewyork.us)
  Other → County assessor + generic fallback (returns empty gracefully)

Output: .tmp/permits.json
  [
    {
      "permit_id": "...",
      "permit_type": "New Building | Alteration | Demolition",
      "status": "...",
      "file_date": "YYYY-MM-DD",
      "job_value": 0.0,
      "applicant_name": "...",
      "applicant_title": "Architect | Engineer | Owner",
      "owner_name": "...",
      "contractor_name": "...",
      "source": "NYC_DOB | Generic"
    }
  ]
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.parent
TMP = BASE / ".tmp"
INPUT_PATH = TMP / "normalized_address.json"
OUTPUT_PATH = TMP / "permits.json"

# NYC DOB job filings dataset (Socrata — no API key needed, 1000 req/day limit)
NYC_DOB_URL = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
# NYC DOB NOW Build (newer permits, post-2016)
NYC_DOB_NOW_URL = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"

BOROUGH_MAP = {
    "MANHATTAN": "MANHATTAN",
    "NEW YORK": "MANHATTAN",
    "NY": "MANHATTAN",
    "BROOKLYN": "BROOKLYN",
    "QUEENS": "QUEENS",
    "BRONX": "BRONX",
    "STATEN ISLAND": "STATEN ISLAND",
}


def _fetch_url(url: str) -> list[dict]:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        print(f"[permit_scraper] HTTP error: {exc}", file=sys.stderr)
        return []


def _normalize_street(street: str) -> str:
    """Strip number prefix and clean up street name for matching."""
    parts = street.upper().split()
    # Remove leading house number if present
    if parts and parts[0].isdigit():
        parts = parts[1:]
    return " ".join(parts)


def _fetch_nyc_dob(house_number: str, street_name: str, borough: str) -> list[dict]:
    """
    Query NYC DOB Job Application Filings by address.
    Returns list of raw permit records.
    """
    clean_street = _normalize_street(street_name)
    borough_upper = borough.upper().strip()

    params = urllib.parse.urlencode({
        "$where": (
            f"upper(street_name) like '%{clean_street}%' "
            f"AND upper(borough) = '{borough_upper}'"
        ),
        "$limit": "50",
        "$order": "latest_action_date DESC",
    })
    url = f"{NYC_DOB_URL}?{params}"
    print(f"[permit_scraper] Querying NYC DOB: {clean_street}, {borough_upper}")
    results = _fetch_url(url)

    # Filter by house number if we got results
    if house_number and results:
        filtered = [
            r for r in results
            if str(r.get("house__", "")).strip() == str(house_number).strip()
        ]
        if filtered:
            results = filtered

    return results


def _fetch_nyc_dob_now(house_number: str, street_name: str, borough: str) -> list[dict]:
    """
    Query NYC DOB NOW Build (newer permits).
    """
    clean_street = _normalize_street(street_name)

    params = urllib.parse.urlencode({
        "$where": (
            f"upper(job_filing_number) IS NOT NULL "
            f"AND upper(building_identification_number) IS NOT NULL"
        ),
        "$q": f"{house_number} {clean_street}",
        "$limit": "20",
    })
    url = f"{NYC_DOB_NOW_URL}?{params}"
    print(f"[permit_scraper] Querying NYC DOB NOW: {house_number} {clean_street}")
    return _fetch_url(url)


def _parse_nyc_dob_record(r: dict) -> dict:
    """Normalise a raw NYC DOB record into our permit schema."""
    applicant_name = " ".join(filter(None, [
        r.get("applicant_s_first_name", ""),
        r.get("applicant_s_last_name", ""),
    ])).strip()

    owner_name = (
        r.get("owner_s_business_name", "")
        or " ".join(filter(None, [
            r.get("owner_s_first_name", ""),
            r.get("owner_s_last_name", ""),
        ])).strip()
    )

    # Derive permit type from job_type code
    job_type_map = {
        "NB": "New Building",
        "A1": "Major Alteration",
        "A2": "Minor Alteration",
        "A3": "Minor Alteration",
        "DM": "Demolition",
        "SG": "Sign",
        "FO": "Foundation",
        "BL": "Boiler",
        "EQ": "Equipment",
    }
    job_code = r.get("job_type", "").upper()
    permit_type = job_type_map.get(job_code, r.get("job_type", "Unknown"))

    return {
        "permit_id": r.get("job__", r.get("job_filing_number", "")),
        "permit_type": permit_type,
        "status": r.get("job_status", r.get("filing_status", "")),
        "file_date": r.get("pre__filing_date", r.get("latest_action_date", "")),
        "job_value": _safe_float(r.get("initial_cost", r.get("job_value_cost", 0))),
        "applicant_name": applicant_name,
        "applicant_title": r.get("applicant_professional_title", ""),
        "owner_name": owner_name,
        "contractor_name": r.get("contractor_s_business_name", ""),
        "contractor_license": r.get("contractor_s_license__", ""),
        "source": "NYC_DOB",
    }


def _safe_float(val: object) -> float | None:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _detect_city(addr: dict) -> str:
    """Return city identifier from normalized address."""
    city = addr.get("city", "").upper()
    state = addr.get("state", "").upper()

    nyc_cities = {"NEW YORK", "MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND", "NEW YORK CITY"}
    if city in nyc_cities or (state == "NY" and city in nyc_cities):
        return "NYC"

    return "GENERIC"


def _parse_house_and_street(delivery_line: str) -> tuple[str, str]:
    """
    Split '123 MAIN ST STE 200' into ('123', 'MAIN ST').
    Returns (house_number, street_name).
    """
    parts = delivery_line.strip().split()
    if not parts:
        return "", delivery_line
    if parts[0].isdigit() or (len(parts[0]) > 1 and parts[0][:-1].isdigit()):
        house = parts[0]
        street = " ".join(parts[1:])
        # Strip unit suffixes (STE, APT, UNIT, #)
        for suffix in ["STE", "APT", "UNIT", "FL", "FLOOR", "#"]:
            if suffix in street.upper().split():
                idx = street.upper().split().index(suffix)
                street = " ".join(street.split()[:idx])
                break
        return house, street
    return "", delivery_line


def scrape_permits(addr: dict) -> list[dict]:
    """Main entry point. Returns list of permit dicts."""
    city = _detect_city(addr)
    delivery = addr.get("delivery_line_1", "")
    house, street = _parse_house_and_street(delivery)
    state = addr.get("state", "").upper()

    print(f"[permit_scraper] City detected: {city}")
    print(f"[permit_scraper] Address: house='{house}' street='{street}'")

    if city == "NYC":
        # Determine borough from city field
        city_field = addr.get("city", "MANHATTAN").upper()
        borough = BOROUGH_MAP.get(city_field, "MANHATTAN")

        raw = _fetch_nyc_dob(house, street, borough)
        permits = [_parse_nyc_dob_record(r) for r in raw]

        print(f"[permit_scraper] NYC DOB returned {len(permits)} permit(s)")
        return permits

    # Generic fallback — other cities
    print(f"[permit_scraper] No free permit API configured for {addr.get('city')}, {state}")
    print("[permit_scraper] Returning empty — stakeholders will be web-search only")
    return []


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[permit_scraper] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    addr = json.loads(INPUT_PATH.read_text())
    permits = scrape_permits(addr)

    OUTPUT_PATH.write_text(json.dumps(permits, indent=2, default=str))
    print(f"[permit_scraper] {len(permits)} permit(s) → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
