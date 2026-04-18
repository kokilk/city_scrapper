"""
Stage 1A (part 2): Shovels.ai Contractor Profile Fetch

For each unique contractor_id found in permit data, fetches the full
contractor profile (classification, contact, license, permit history).

Input:  .tmp/shovels_permits.json
Output: .tmp/shovels_contractors.json  (dict keyed by contractor_id)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from models import ContractorProfile, SourceReference
from api_client import api_session, get_json, SHOVELS_SEM

load_dotenv()

BASE_URL = "https://api.shovels.ai/v2"
INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "shovels_permits.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "shovels_contractors.json"
MAX_CONCURRENT = 10


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _parse_contractor(cid: str, raw: dict[str, Any]) -> ContractorProfile:
    return ContractorProfile(
        contractor_id=cid,
        biz_name=raw.get("biz_name", "") or "",
        classification_derived=raw.get("classification_derived", "") or "",
        primary_email=raw.get("primary_email", "") or "",
        primary_phone=raw.get("primary_phone", "") or "",
        website=raw.get("website", "") or "",
        linkedin_url=raw.get("linkedin_url", "") or "",
        license_number=raw.get("license", "") or "",
        license_exp_date=_parse_date(raw.get("license_exp_date")),
        license_status=raw.get("status_detailed", "") or "",
        permit_count=int(raw.get("permit_count", 0) or 0),
        avg_job_value=raw.get("avg_job_value"),
        source=SourceReference(
            source_name="Shovels",
            record_id=cid,
            record_date=date.today(),
            raw_url=f"{BASE_URL}/contractors/{cid}",
        ),
    )


async def fetch_one(
    session: Any,
    cid: str,
    headers: dict[str, str],
    sem: asyncio.Semaphore,
) -> tuple[str, dict[str, Any] | None]:
    try:
        data = await get_json(
            session,
            f"{BASE_URL}/contractors/{cid}",
            headers=headers,
            sem=sem,
        )
        profile = _parse_contractor(cid, data)  # type: ignore[arg-type]
        return cid, asdict(profile)
    except Exception as exc:
        print(f"[shovels_contractor_fetch] ERROR for contractor {cid}: {exc}", file=sys.stderr)
        return cid, None


async def fetch_contractors(contractor_ids: list[str]) -> dict[str, Any]:
    api_key = os.getenv("SHOVELS_API_KEY", "")
    if not api_key:
        print("[shovels_contractor_fetch] WARNING: SHOVELS_API_KEY not set — skipping", file=sys.stderr)
        return {}

    headers = {"X-API-Key": api_key}
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results: dict[str, Any] = {}

    async with api_session() as session:
        tasks = [
            fetch_one(session, cid, headers, sem)
            for cid in contractor_ids
        ]
        for cid, profile in await asyncio.gather(*tasks):
            if profile is not None:
                results[cid] = profile

    return results


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[shovels_contractor_fetch] No permits file at {INPUT_PATH}", file=sys.stderr)
        OUTPUT_PATH.write_text("{}")
        return

    permits: list[dict[str, Any]] = json.loads(INPUT_PATH.read_text())
    contractor_ids = list({
        p["contractor_id"]
        for p in permits
        if p.get("contractor_id")
    })

    if not contractor_ids:
        print("[shovels_contractor_fetch] No contractor IDs found in permits")
        OUTPUT_PATH.write_text("{}")
        return

    print(f"[shovels_contractor_fetch] Fetching {len(contractor_ids)} contractor profile(s)…")
    contractors = asyncio.run(fetch_contractors(contractor_ids))

    OUTPUT_PATH.write_text(json.dumps(contractors, indent=2, default=str))
    print(f"[shovels_contractor_fetch] Fetched {len(contractors)} profile(s) → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
