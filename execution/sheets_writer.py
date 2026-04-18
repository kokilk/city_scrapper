"""
Stage 7: Google Sheets Writer

Writes the final stakeholder list to a Google Sheet tab.
Tab name: {AddressSlug}_{YYYY-MM-DD}  e.g. 123MainSt90210_2026-04-08

Behavior:
  - If tab already exists: clears data rows (A2:Z) and rewrites (idempotent)
  - If tab doesn't exist: creates it, freezes row 1, applies conditional formatting,
    enables auto-filter, then writes data
  - Uses batch_update() for all rows in one API call

Authentication: Google service account (credentials.json).
No browser OAuth flow — safe for headless / automated execution.

Prerequisites:
  1. Create a Google Cloud project and enable the Google Sheets API
  2. Create a service account and download credentials.json to the project root
  3. Share your target spreadsheet with the service account email (editor access)
  4. Set GOOGLE_SHEET_ID in .env

Input:  .tmp/final_stakeholders.json, .tmp/normalized_address.json
Output: Google Sheet tab (prints URL to stdout)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

FINAL_PATH = Path(__file__).parent.parent / ".tmp" / "final_stakeholders.json"
ADDR_PATH = Path(__file__).parent.parent / ".tmp" / "normalized_address.json"
CREDS_PATH = Path(__file__).parent.parent / "credentials.json"

# ── Column definitions (order = column index, A=0) ────────────────────────────
HEADERS = [
    "Property Address",    # A
    "Role",                # B
    "Full Name",           # C
    "Company",             # D
    "Phone",               # E
    "Email",               # F
    "LinkedIn URL",        # G
    "Website",             # H
    "Confidence Score",    # I
    "Confidence Label",    # J
    "Sources",             # K
    "Permit Number",       # L
    "Permit Date",         # M
    "Permit Type",         # N
    "Notes / Flags",       # O
    "Last Verified Date",  # P
]

# Confidence Score is now column I (index 8)
CONFIDENCE_COL_INDEX = 8


def _col_letter(idx: int) -> str:
    """Convert 0-based column index to spreadsheet letter (0→A, 25→Z, 26→AA)."""
    result = ""
    while True:
        result = chr(ord("A") + idx % 26) + result
        idx = idx // 26 - 1
        if idx < 0:
            break
    return result


def _stakeholder_to_row(s: dict[str, Any], property_address: str) -> list[Any]:
    """Map a stakeholder dict to a list of values in HEADERS column order."""
    source_records = s.get("source_records", [])
    sources = "|".join(sorted({r.get("source_name", "") for r in source_records}))

    # Merge enrichment sources too
    enrichment = s.get("enrichment_sources", [])
    all_sources = sorted({r.get("source_name", "") for r in source_records} | set(enrichment))
    sources = "|".join(s for s in all_sources if s)

    flags = s.get("flags", [])
    notes = "|".join(flags) if flags else ""

    return [
        property_address,
        s.get("role", ""),
        s.get("raw_name", ""),
        s.get("company", ""),
        s.get("phone", ""),
        s.get("email", ""),
        s.get("linkedin_url", ""),
        s.get("website", ""),
        s.get("confidence_score", 0),
        s.get("confidence_label", "Unconfirmed"),
        sources,
        s.get("permit_number", ""),
        str(s.get("permit_date", "") or ""),
        s.get("permit_type", ""),
        notes,
        str(date.today()),
    ]


def _build_conditional_format_requests(sheet_id: int) -> list[dict[str, Any]]:
    """
    Column I (index 8) = Confidence Score.
    Green ≥75, Yellow 45-74, Red <45.
    """
    h_col = CONFIDENCE_COL_INDEX  # 0-based

    def rule(min_val: float, max_val: float | None, color: dict[str, float]) -> dict[str, Any]:
        condition_values = [{"userEnteredValue": str(min_val)}]
        condition_type = "NUMBER_GREATER_THAN_EQ"
        if max_val is not None:
            condition_type = "NUMBER_BETWEEN"
            condition_values.append({"userEnteredValue": str(max_val)})
        return {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": sheet_id,
                        "startRowIndex": 1,       # data rows only
                        "startColumnIndex": h_col,
                        "endColumnIndex": h_col + 1,
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": condition_type,
                            "values": condition_values,
                        },
                        "format": {"backgroundColor": color},
                    },
                },
                "index": 0,
            }
        }

    return [
        rule(75, None, {"red": 0.565, "green": 0.933, "blue": 0.565}),   # green
        rule(45, 74, {"red": 1.0, "green": 0.961, "blue": 0.549}),       # yellow
        rule(0, 44, {"red": 1.0, "green": 0.541, "blue": 0.541}),        # red
    ]


def write_to_sheet(
    stakeholders: list[dict[str, Any]],
    property_address: str,
    sheet_id: str,
    tab_name: str,
) -> str:
    """
    Write data to Google Sheet. Returns the sheet URL.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise RuntimeError(
            "gspread and google-auth are required: pip install gspread google-auth"
        )

    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDS_PATH}. "
            "Create a service account at console.cloud.google.com and download the key."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(sheet_id)

    # Get or create the tab
    try:
        worksheet = spreadsheet.worksheet(tab_name)
        # Tab exists — clear data rows
        last_col = _col_letter(len(HEADERS) - 1)
        worksheet.batch_clear([f"A2:{last_col}"])
        created_new = False
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(HEADERS))
        created_new = True

    # Write headers
    worksheet.update("A1", [HEADERS])

    # Write data rows
    if stakeholders:
        rows = [
            _stakeholder_to_row(s, property_address)
            for s in stakeholders
        ]
        worksheet.update("A2", rows)

    # One-time setup for new tabs
    if created_new:
        sheet_meta_id = worksheet.id
        requests = [
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_meta_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            # Enable auto-filter on header row
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": sheet_meta_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(HEADERS),
                        }
                    }
                }
            },
        ]
        requests.extend(_build_conditional_format_requests(sheet_meta_id))
        spreadsheet.batch_update({"requests": requests})

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={worksheet.id}"
    return url


def main() -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        print("[sheets_writer] ERROR: GOOGLE_SHEET_ID not set in .env", file=sys.stderr)
        sys.exit(1)

    if not FINAL_PATH.exists():
        print(f"[sheets_writer] ERROR: {FINAL_PATH} not found", file=sys.stderr)
        sys.exit(1)

    stakeholders = json.loads(FINAL_PATH.read_text())

    addr = {}
    if ADDR_PATH.exists():
        addr = json.loads(ADDR_PATH.read_text())

    property_address = (
        f"{addr.get('delivery_line_1', '')}, "
        f"{addr.get('city', '')}, "
        f"{addr.get('state', '')} {addr.get('zip5', '')}"
    ).strip(", ")
    county_fips = addr.get("county_fips", "")

    # Derive slug for tab name from address
    import re
    slug = re.sub(r"[^A-Za-z0-9]", "", property_address.title())[:30]
    tab_name = f"{slug}_{date.today()}"

    raw_data_path = str(FINAL_PATH.resolve())

    print(f"[sheets_writer] Writing {len(stakeholders)} rows to tab '{tab_name}'…")
    try:
        url = write_to_sheet(
            stakeholders,
            property_address,
            sheet_id,
            tab_name,
        )
        print(f"[sheets_writer] ✓ Sheet written: {url}")
    except Exception as exc:
        print(f"[sheets_writer] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
