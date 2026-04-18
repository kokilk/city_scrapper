"""
Stage 1C: OpenCorporates — Entity & Officer Lookup

For each entity name (LLC, LP, Corp, etc.) detected in permit and ownership data,
queries OpenCorporates to find officers (managing members, directors, agents).
This pierces LLC veils to find the human decision-makers.

Input:  .tmp/shovels_permits.json, .tmp/attom_property.json
Output: .tmp/opencorporates_entities.json  (dict keyed by entity_name)

Rate limiting: Free tier = 200 req/mo, 50/day.
This script tracks daily usage in .tmp/opencorporates_usage.json and skips
queries once the daily limit is approached (leaves a buffer of 5).

OpenCorporates API docs: https://api.opencorporates.com/documentation
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from models import CompanyRecord, CompanyOfficer, SourceReference
from api_client import sync_get_json

load_dotenv()

BASE_URL = "https://api.opencorporates.com/v0.4"
DAILY_LIMIT = 45          # stay under 50/day free tier with buffer
USAGE_PATH = Path(__file__).parent.parent / ".tmp" / "opencorporates_usage.json"

PERMITS_PATH = Path(__file__).parent.parent / ".tmp" / "shovels_permits.json"
ATTOM_PATH = Path(__file__).parent.parent / ".tmp" / "attom_property.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "opencorporates_entities.json"

# Regex to detect legal entity suffixes
ENTITY_RE = re.compile(
    r"\b(LLC|L\.L\.C|LP|L\.P|LLP|L\.L\.P|Inc\.?|Corp\.?|Trust|REIT|"
    r"Foundation|Holdings|Partners|Partnership|Realty|Properties|Group)\b",
    re.IGNORECASE,
)

# US state abbreviation → OpenCorporates jurisdiction code
STATE_TO_JURISDICTION: dict[str, str] = {
    "AL": "us_al", "AK": "us_ak", "AZ": "us_az", "AR": "us_ar", "CA": "us_ca",
    "CO": "us_co", "CT": "us_ct", "DE": "us_de", "FL": "us_fl", "GA": "us_ga",
    "HI": "us_hi", "ID": "us_id", "IL": "us_il", "IN": "us_in", "IA": "us_ia",
    "KS": "us_ks", "KY": "us_ky", "LA": "us_la", "ME": "us_me", "MD": "us_md",
    "MA": "us_ma", "MI": "us_mi", "MN": "us_mn", "MS": "us_ms", "MO": "us_mo",
    "MT": "us_mt", "NE": "us_ne", "NV": "us_nv", "NH": "us_nh", "NJ": "us_nj",
    "NM": "us_nm", "NY": "us_ny", "NC": "us_nc", "ND": "us_nd", "OH": "us_oh",
    "OK": "us_ok", "OR": "us_or", "PA": "us_pa", "RI": "us_ri", "SC": "us_sc",
    "SD": "us_sd", "TN": "us_tn", "TX": "us_tx", "UT": "us_ut", "VT": "us_vt",
    "VA": "us_va", "WA": "us_wa", "WV": "us_wv", "WI": "us_wi", "WY": "us_wy",
}


def _load_usage() -> dict[str, Any]:
    if USAGE_PATH.exists():
        data = json.loads(USAGE_PATH.read_text())
        if data.get("date") == str(date.today()):
            return data
    return {"date": str(date.today()), "count": 0}


def _save_usage(usage: dict[str, Any]) -> None:
    USAGE_PATH.write_text(json.dumps(usage))


def _is_entity(name: str) -> bool:
    return bool(ENTITY_RE.search(name))


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _parse_company(raw_company: dict[str, Any]) -> CompanyRecord:
    officers_raw = raw_company.get("officers", [])
    officers = []
    for o in officers_raw:
        off = o.get("officer", o)
        officers.append(CompanyOfficer(
            name=off.get("name", ""),
            position=off.get("position", "") or "",
            start_date=_parse_date(off.get("start_date")),
            end_date=_parse_date(off.get("end_date")),
            address=off.get("address", "") or "",
        ))

    return CompanyRecord(
        company_name=raw_company.get("name", ""),
        company_number=raw_company.get("company_number", ""),
        jurisdiction=raw_company.get("jurisdiction_code", ""),
        company_type=raw_company.get("company_type", "") or "",
        incorporation_date=_parse_date(raw_company.get("incorporation_date")),
        status=raw_company.get("current_status", "") or "",
        registered_agent=raw_company.get("registered_agent_name", "") or "",
        officers=officers,
        source=SourceReference(
            source_name="OpenCorporates",
            record_id=raw_company.get("company_number", ""),
            record_date=date.today(),
            raw_url=raw_company.get("opencorporates_url", ""),
        ),
    )


def lookup_entity(
    entity_name: str,
    state: str,
    api_key: str,
    usage: dict[str, Any],
) -> dict[str, Any] | None:
    if usage["count"] >= DAILY_LIMIT:
        print(
            f"[opencorporates] Daily limit ({DAILY_LIMIT}) reached — skipping '{entity_name}'",
            file=sys.stderr,
        )
        return None

    jurisdiction = STATE_TO_JURISDICTION.get(state.upper(), "us")
    params: dict[str, Any] = {
        "q": entity_name,
        "jurisdiction_code": jurisdiction,
        "current_status": "Active",
    }
    if api_key:
        params["api_token"] = api_key

    try:
        data = sync_get_json(f"{BASE_URL}/companies/search", params=params)
        usage["count"] += 1
        _save_usage(usage)

        companies = (
            data.get("results", {}).get("companies", [])  # type: ignore[union-attr]
            if isinstance(data, dict)
            else []
        )

        if not companies:
            return None

        # Take best match: first active company
        for item in companies:
            raw_company = item.get("company", item)
            if raw_company.get("company_number"):
                # Fetch with officers using detail endpoint
                detail_url = f"{BASE_URL}/companies/{raw_company['jurisdiction_code']}/{raw_company['company_number']}"
                if api_key:
                    detail_url += f"?api_token={api_key}"
                try:
                    detail = sync_get_json(detail_url)
                    usage["count"] += 1
                    _save_usage(usage)
                    rc = (
                        detail.get("results", {}).get("company", {})
                        if isinstance(detail, dict)
                        else {}
                    )
                    record = _parse_company(rc)
                    return asdict(record)
                except Exception:
                    record = _parse_company(raw_company)
                    return asdict(record)

        return None
    except Exception as exc:
        print(f"[opencorporates] ERROR for '{entity_name}': {exc}", file=sys.stderr)
        usage["count"] += 1
        _save_usage(usage)
        return None


def extract_entity_names(permits: list[dict[str, Any]], attom: dict[str, Any]) -> set[str]:
    names: set[str] = set()

    for permit in permits:
        for field in ("applicant_name", "owner_name"):
            val = permit.get(field, "")
            if val and _is_entity(val):
                names.add(val.strip())

    # ATTOM owner
    owner = attom.get("owner_full_name", "")
    if owner and _is_entity(owner):
        names.add(owner.strip())

    return names


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("OPENCORPORATES_API_KEY", "")
    usage = _load_usage()

    permits: list[dict[str, Any]] = []
    attom: dict[str, Any] = {}

    if PERMITS_PATH.exists():
        permits = json.loads(PERMITS_PATH.read_text())
    if ATTOM_PATH.exists():
        attom = json.loads(ATTOM_PATH.read_text())

    # Infer state from ATTOM or permits
    state = attom.get("source", {}).get("record_id", "")[-2:] or "CA"
    # Better: use normalized_address for state
    addr_path = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"
    if addr_path.exists():
        addr = json.loads(addr_path.read_text())
        state = addr.get("state", "CA")

    entity_names = extract_entity_names(permits, attom)

    if not entity_names:
        print("[opencorporates] No entity names detected — skipping")
        OUTPUT_PATH.write_text("{}")
        return

    print(f"[opencorporates] Looking up {len(entity_names)} entity name(s)…")
    results: dict[str, Any] = {}

    for name in entity_names:
        result = lookup_entity(name, state, api_key, usage)
        if result:
            results[name] = result
            print(f"[opencorporates] ✓ {name} → {result.get('company_name', '')}")
        else:
            print(f"[opencorporates] – {name}: no match or limit reached")

    OUTPUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"[opencorporates] {len(results)} record(s) → {OUTPUT_PATH}")
    print(f"[opencorporates] API calls used today: {usage['count']}/{DAILY_LIMIT}")


if __name__ == "__main__":
    main()
