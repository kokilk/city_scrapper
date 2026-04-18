"""
Stage 1B: ATTOM Data Solutions — Property Owner & Mortgage Fetch

Fetches deed owner, lender, loan amount, and sale history for the property.
This is the ground truth for legal ownership and recorded mortgages.

Input:  .tmp/normalized_address.json
Output: .tmp/attom_property.json  (PropertyRecord-compatible dict, or {} on failure)

ATTOM API docs: https://api.attomdata.com/swagger/index.html
Endpoint: GET /property/detailmortgageowner
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from models import PropertyRecord, SourceReference
from api_client import sync_get_json

load_dotenv()

BASE_URL = "https://api.attomdata.com/propertyapi/v1.0.0"
INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "attom_property.json"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        return None


def _parse_property(raw: dict[str, Any]) -> PropertyRecord:
    """Extract owner and mortgage fields from ATTOM response."""
    prop = raw.get("property", [{}])
    if isinstance(prop, list):
        prop = prop[0] if prop else {}

    identifier = prop.get("identifier", {})
    assessment = prop.get("assessment", {})
    sale = prop.get("sale", {})
    owner = prop.get("owner", {})
    mortgage = prop.get("mortgage", {})

    parcel_id = identifier.get("attomId", str(identifier.get("apn", "")))

    # Owner name: ATTOM returns owner1LastName + owner1FirstName
    owner_last = owner.get("owner1LastName", "")
    owner_first = owner.get("owner1FirstName", "")
    owner_full = f"{owner_first} {owner_last}".strip() or owner.get("corporateName", "")

    lender = mortgage.get("lenderName", "") or mortgage.get("firstLenderName", "")
    loan_amount = _safe_float(
        mortgage.get("amount1stMtge") or mortgage.get("loanAmount")
    )

    return PropertyRecord(
        owner_full_name=owner_full,
        owner_mailing_address=owner.get("mailingAddressOneLine", ""),
        lender_name=lender,
        loan_amount=loan_amount,
        loan_type=mortgage.get("loanType1stMtge", "") or "",
        loan_term=str(mortgage.get("loanTermMonths1stMtge", "") or ""),
        last_sale_date=_parse_date(sale.get("salesDate") or sale.get("saleTransDate")),
        last_sale_price=_safe_float(sale.get("salesAmt") or sale.get("amount", {}).get("saleAmt")),
        deed_type=sale.get("deedType", "") or "",
        source=SourceReference(
            source_name="ATTOM",
            record_id=parcel_id,
            record_date=_parse_date(sale.get("salesDate")) or date.today(),
            raw_url=f"{BASE_URL}/property/detailmortgageowner",
        ),
    )


def fetch(addr: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("ATTOM_API_KEY", "")
    if not api_key:
        print("[attom_property_fetch] WARNING: ATTOM_API_KEY not set — skipping", file=sys.stderr)
        return {"_status": "SKIPPED", "_reason": "No API key"}

    headers = {
        "apikey": api_key,
        "Accept": "application/json",
    }
    params = {
        "address1": addr["delivery_line_1"],
        "address2": f"{addr['city']}, {addr['state']} {addr['zip5']}",
    }

    try:
        data = sync_get_json(
            f"{BASE_URL}/property/detailmortgageowner",
            headers=headers,
            params=params,
        )
        record = _parse_property(data)
        result = asdict(record)
        result["_status"] = "OK"
        return result
    except Exception as exc:
        print(f"[attom_property_fetch] ERROR: {exc}", file=sys.stderr)
        return {"_status": "FAILED", "_reason": str(exc)}


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[attom_property_fetch] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        OUTPUT_PATH.write_text(json.dumps({"_status": "FAILED", "_reason": "No address input"}))
        sys.exit(1)

    addr = json.loads(INPUT_PATH.read_text())
    result = fetch(addr)

    OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"[attom_property_fetch] Status={result['_status']} → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
