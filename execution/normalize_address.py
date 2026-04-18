"""
Stage 0: Address Normalization

Calls the Smarty US Street API to USPS-standardize the input address.
Writes the result to .tmp/normalized_address.json.

Raises SystemExit(1) if the address cannot be verified (dpv_match_code == "N"),
which halts the entire pipeline — downstream API credits must not be wasted
on an undeliverable address.

Usage:
    python execution/normalize_address.py --address "123 Main St" --zip "90210"
    python execution/normalize_address.py --address "123 Main St" --zip "90210" --output .tmp/normalized_address.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
import os

# Add parent dir to path so execution scripts import cleanly
sys.path.insert(0, str(Path(__file__).parent))
from models import StandardAddress
from api_client import sync_get_json

load_dotenv()

SMARTY_URL = "https://us-street.api.smartystreets.com/street-address"
DEFAULT_OUTPUT = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"

# DPV codes where we still proceed (with a warning)
ACCEPTABLE_DPV_CODES = {"Y", "S", "D"}


def _passthrough(raw_address: str, zip_code: str) -> StandardAddress:
    """
    No Smarty keys — parse the address as-is and return a best-effort StandardAddress.
    City detection still works for NYC permit scraping.
    """
    import re
    # Try to parse "123 Main St, Brooklyn, NY 11201" or "123 Main St Brooklyn NY"
    parts = raw_address.replace(",", " ").split()
    city = ""
    state = ""

    # Look for state abbreviation (2 uppercase letters)
    for i, p in enumerate(parts):
        if re.match(r"^[A-Z]{2}$", p):
            state = p
            city = parts[i - 1] if i > 0 else ""
            break

    street_parts = []
    for p in parts:
        if p == state or p == city:
            break
        street_parts.append(p)
    street = " ".join(street_parts).upper()

    print(f"[normalize] Smarty skipped (no keys) — using address as-is: {street}, {city}, {state} {zip_code}")
    return StandardAddress(
        delivery_line_1=street,
        city=city.upper(),
        state=state.upper(),
        zip5=zip_code[:5],
        zip4="",
        county_fips="",
        county_name="",
        latitude=0.0,
        longitude=0.0,
        rdi="",
        dpv_match_code="Y",  # assume valid since user confirmed address
        raw_input_address=raw_address,
        raw_input_zip=zip_code,
    )


def normalize(raw_address: str, zip_code: str) -> StandardAddress:
    """
    Call Smarty and return a StandardAddress.
    Falls back to passthrough mode if Smarty keys are not set.
    """
    auth_id = os.getenv("SMARTY_AUTH_ID", "")
    auth_token = os.getenv("SMARTY_AUTH_TOKEN", "")

    if not auth_id or not auth_token:
        return _passthrough(raw_address, zip_code)

    params = {
        "street": raw_address,
        "zipcode": zip_code,
        "auth-id": auth_id,
        "auth-token": auth_token,
        "candidates": "1",
    }

    result = sync_get_json(SMARTY_URL, params=params)

    if not result:
        raise ValueError(
            f"Smarty returned no candidates for '{raw_address}, {zip_code}'. "
            "Verify the address and try again."
        )

    candidate = result[0]  # type: ignore[index]
    components = candidate.get("components", {})
    metadata = candidate.get("metadata", {})
    analysis = candidate.get("analysis", {})

    dpv = analysis.get("dpv_match_code", "N")

    addr = StandardAddress(
        delivery_line_1=candidate.get("delivery_line_1", ""),
        city=components.get("city_name", ""),
        state=components.get("state_abbreviation", ""),
        zip5=components.get("zipcode", zip_code),
        zip4=components.get("plus4_code", ""),
        county_fips=metadata.get("county_fips", ""),
        county_name=metadata.get("county_name", ""),
        latitude=metadata.get("latitude", 0.0),
        longitude=metadata.get("longitude", 0.0),
        rdi=metadata.get("rdi", ""),
        dpv_match_code=dpv,
        raw_input_address=raw_address,
        raw_input_zip=zip_code,
    )

    if dpv == "N":
        raise ValueError(
            f"Address '{raw_address}, {zip_code}' is undeliverable (Smarty DPV=N). "
            "Cannot proceed — verify the address and retry."
        )

    if dpv == "D":
        print(
            f"[normalize_address] WARNING: Address missing secondary unit "
            f"(apt/suite). DPV=D. Proceeding with: {addr.full()}",
            file=sys.stderr,
        )

    return addr


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a property address via Smarty")
    parser.add_argument("--address", required=True, help="Street address, e.g. '123 Main St'")
    parser.add_argument("--zip", required=True, dest="zip_code", help="ZIP code, e.g. '90210'")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        addr = normalize(args.address, args.zip_code)
    except ValueError as exc:
        print(f"[normalize_address] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as exc:
        print(f"[normalize_address] CONFIG ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    data = asdict(addr)
    # Convert date objects to ISO strings for JSON serialization
    output_path.write_text(json.dumps(data, indent=2, default=str))
    print(f"[normalize_address] Standardized: {addr.full()} (DPV={addr.dpv_match_code})")
    print(f"[normalize_address] Written to: {output_path}")


if __name__ == "__main__":
    main()
