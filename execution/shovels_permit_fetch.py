"""
Stage 1A (part 1): Shovels.ai Permit Fetch

Fetches all building permits for a normalized address from Shovels.ai.
Paginates until exhausted or 200 permits reached (prevents runaway on high-density
addresses like apartment complexes).

Input:  .tmp/normalized_address.json
Output: .tmp/shovels_permits.json  (list of PermitRecord-compatible dicts)

Shovels API docs: https://docs.shovels.ai
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
from models import PermitRecord, SourceReference
from api_client import api_session, get_json, SHOVELS_SEM

load_dotenv()

BASE_URL = "https://api.shovels.ai/v2"
MAX_PERMITS = 200
PAGE_SIZE = 50
INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "shovels_permits.json"


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _parse_permit(raw: dict[str, Any], address: str) -> PermitRecord:
    permit_id = str(raw.get("id", ""))
    return PermitRecord(
        permit_id=permit_id,
        file_date=_parse_date(raw.get("file_date")),
        issue_date=_parse_date(raw.get("issue_date")),
        job_value=raw.get("job_value"),
        status=raw.get("status", ""),
        permit_type=_join_tags(raw.get("tags", [])),
        applicant_name=raw.get("applicant_name", ""),
        applicant_email=raw.get("applicant_email", "") or "",
        applicant_phone=raw.get("applicant_phone", "") or "",
        owner_name=raw.get("owner_name", "") or "",
        owner_email=raw.get("owner_email", "") or "",
        owner_phone=raw.get("owner_phone", "") or "",
        contractor_id=str(raw.get("contractor_id", "")) or "",
        source=SourceReference(
            source_name="Shovels",
            record_id=permit_id,
            record_date=_parse_date(raw.get("issue_date") or raw.get("file_date")) or date.today(),
            raw_url=f"{BASE_URL}/permits/{permit_id}",
        ),
    )


def _join_tags(tags: list[str] | None) -> str:
    if not tags:
        return ""
    return "|".join(tags)


async def fetch_permits(addr: dict[str, Any]) -> list[dict[str, Any]]:
    api_key = os.getenv("SHOVELS_API_KEY", "")
    if not api_key:
        print("[shovels_permit_fetch] WARNING: SHOVELS_API_KEY not set — skipping", file=sys.stderr)
        return []

    headers = {"X-API-Key": api_key}
    # Shovels accepts full address string for address search
    full_address = f"{addr['delivery_line_1']}, {addr['city']}, {addr['state']} {addr['zip5']}"

    permits: list[dict[str, Any]] = []
    page = 1

    async with api_session() as session:
        while len(permits) < MAX_PERMITS:
            params = {
                "address": full_address,
                "status": "final,active,in_review",
                "page": page,
                "size": PAGE_SIZE,
            }
            try:
                data = await get_json(
                    session,
                    f"{BASE_URL}/permits",
                    headers=headers,
                    params=params,
                    sem=SHOVELS_SEM,
                )
            except Exception as exc:
                print(f"[shovels_permit_fetch] ERROR on page {page}: {exc}", file=sys.stderr)
                break

            # Shovels returns {"items": [...], "total": N} or just a list
            if isinstance(data, list):
                items = data
            else:
                items = data.get("items", data.get("permits", []))  # type: ignore[union-attr]

            if not items:
                break

            for raw in items:
                try:
                    permit = _parse_permit(raw, full_address)
                    permits.append(asdict(permit))
                except Exception as exc:
                    print(f"[shovels_permit_fetch] Parse error on permit: {exc}", file=sys.stderr)

            # If fewer than PAGE_SIZE items returned, we've exhausted results
            if len(items) < PAGE_SIZE:
                break
            page += 1

    return permits


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[shovels_permit_fetch] ERROR: {INPUT_PATH} not found. Run normalize_address.py first.", file=sys.stderr)
        sys.exit(1)

    addr = json.loads(INPUT_PATH.read_text())
    permits = asyncio.run(fetch_permits(addr))

    OUTPUT_PATH.write_text(json.dumps(permits, indent=2, default=str))
    print(f"[shovels_permit_fetch] Fetched {len(permits)} permit(s) → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
