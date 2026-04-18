"""
JSON Exporter — outputs clean stakeholder data for n8n / any downstream tool

Reads .tmp/final_stakeholders.json and writes two files:

  output/results.json       — array of flat objects (one per stakeholder)
  output/results_latest.json — same, always overwritten (easy n8n trigger target)

Each object matches the Google Sheet columns exactly:
  property_address, role, full_name, company, phone, email,
  linkedin_url, website, confidence_score, confidence_label,
  sources, permit_number, permit_date, permit_type, notes, last_verified

Usage:
  python3 execution/export_json.py
  (runs automatically at end of pipeline)
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent.parent
TMP = BASE / ".tmp"
OUTPUT_DIR = BASE / "output"

FINAL_PATH = TMP / "final_stakeholders.json"
ADDR_PATH = TMP / "normalized_address.json"


def _flat_row(s: dict[str, Any], property_address: str) -> dict[str, Any]:
    """Convert a stakeholder dict to a flat, clean object for n8n."""
    source_records = s.get("source_records", [])
    enrichment = s.get("enrichment_sources", [])
    all_sources = sorted(
        {r.get("source_name", "") for r in source_records} | set(enrichment)
    )
    sources = " | ".join(src for src in all_sources if src)

    flags = s.get("flags", [])
    notes = " | ".join(flags) if flags else ""

    return {
        "property_address": property_address,
        "role": s.get("role", ""),
        "full_name": s.get("raw_name", ""),
        "company": s.get("company", ""),
        "phone": s.get("phone", ""),
        "email": s.get("email", ""),
        "linkedin_url": s.get("linkedin_url", ""),
        "website": s.get("website", ""),
        "confidence_score": s.get("confidence_score", 0),
        "confidence_label": s.get("confidence_label", "Unconfirmed"),
        "sources": sources,
        "permit_number": s.get("permit_number", ""),
        "permit_date": str(s.get("permit_date", "") or ""),
        "permit_type": s.get("permit_type", ""),
        "notes": notes,
        "last_verified": str(date.today()),
    }


def export() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not FINAL_PATH.exists():
        print(f"[export_json] ERROR: {FINAL_PATH} not found")
        return OUTPUT_DIR / "results.json"

    stakeholders = json.loads(FINAL_PATH.read_text())

    addr = {}
    if ADDR_PATH.exists():
        addr = json.loads(ADDR_PATH.read_text())

    property_address = ", ".join(filter(None, [
        addr.get("delivery_line_1", ""),
        addr.get("city", ""),
        f"{addr.get('state', '')} {addr.get('zip5', '')}".strip(),
    ]))

    rows = [_flat_row(s, property_address) for s in stakeholders]

    # Timestamped file (keeps history)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]", "_", property_address)[:40]
    out_path = OUTPUT_DIR / f"{slug}_{timestamp}.json"
    out_path.write_text(json.dumps(rows, indent=2))

    # Latest file (fixed name — easy for n8n to watch)
    latest_path = OUTPUT_DIR / "results_latest.json"
    latest_path.write_text(json.dumps(rows, indent=2))

    print(f"[export_json] ✓ {len(rows)} stakeholder(s) exported")
    print(f"[export_json]   → {out_path}")
    print(f"[export_json]   → {latest_path}  (latest — use this in n8n)")

    return latest_path


def main() -> None:
    export()


if __name__ == "__main__":
    main()
