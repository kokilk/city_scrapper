"""
Stage 1D: County Assessor Fetch

Uses county_assessor_router to find the right API for the property's county,
then fetches owner name, parcel ID, assessed value, and land use code.
Gracefully skips if the county is not in the router (writes empty result).

Input:  .tmp/normalized_address.json
Output: .tmp/county_assessor.json  (AssessorRecord-compatible dict, or {} if skipped)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from models import AssessorRecord, SourceReference
from county_assessor_router import get_config, resolve_value, AssessorConfig
from api_client import sync_get_json

INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "county_assessor.json"


def _fill_params(template: dict[str, str], address: str, zip5: str) -> dict[str, str]:
    return {
        k: v.replace("{address}", address).replace("{zip5}", zip5)
        for k, v in template.items()
    }


def _safe_float(val: Any) -> float | None:
    try:
        return float(str(val).replace(",", "")) if val not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        return None


def fetch(config: AssessorConfig, addr: dict[str, Any]) -> dict[str, Any]:
    params = _fill_params(
        config.params_template,
        addr["delivery_line_1"],
        addr["zip5"],
    )

    try:
        raw = sync_get_json(config.endpoint_url, params=params)
    except Exception as exc:
        return {"_status": "FAILED", "_reason": str(exc)}

    row = resolve_value(raw, config.result_path)
    if not row:
        return {"_status": "EMPTY", "_reason": "No matching parcel returned"}

    fm = config.field_map
    record = AssessorRecord(
        owner_name=str(row.get(fm.get("owner_name", ""), "") or ""),
        mailing_address=str(row.get(fm.get("mailing_address", ""), "") or ""),
        assessed_value=_safe_float(row.get(fm.get("assessed_value", ""))),
        parcel_id=str(row.get(fm.get("parcel_id", ""), "") or ""),
        land_use_code=str(row.get(fm.get("land_use_code", ""), "") or ""),
        source=SourceReference(
            source_name="CountyAssessor",
            record_id=str(row.get(fm.get("parcel_id", ""), "") or ""),
            record_date=date.today(),
            raw_url=config.endpoint_url,
        ),
    )

    result = asdict(record)
    result["_status"] = "OK"
    result["_county"] = config.county_name
    return result


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[county_assessor_fetch] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        OUTPUT_PATH.write_text(json.dumps({"_status": "SKIPPED", "_reason": "No address input"}))
        return

    addr = json.loads(INPUT_PATH.read_text())
    fips = addr.get("county_fips", "")

    config = get_config(fips)
    if config is None:
        print(f"[county_assessor_fetch] County FIPS {fips} not in router — skipping")
        OUTPUT_PATH.write_text(json.dumps({"_status": "SKIPPED", "_reason": f"County {fips} not supported"}))
        return

    print(f"[county_assessor_fetch] Querying {config.county_name}…")
    result = fetch(config, addr)

    OUTPUT_PATH.write_text(json.dumps(result, indent=2, default=str))
    print(f"[county_assessor_fetch] Status={result['_status']} → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
