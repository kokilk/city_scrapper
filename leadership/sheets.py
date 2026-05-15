"""
Google Sheets integration — appends result rows as batch completes.

Auth: service account JSON file. Path set via GOOGLE_SERVICE_ACCOUNT_FILE env var.
If the env var is not set, all functions are no-ops (silent skip).

Sheet layout:
  Row 1: headers (written once, skipped if already present)
  Row 2+: one row per person found
"""

from __future__ import annotations

import os
import json
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

_lock = threading.Lock()
_client = None
_sheet_cache: dict[str, Any] = {}

HEADERS = [
    "Address", "Company", "Owner Entity", "Source",
    "Company Confidence", "Name", "Title",
    "Email", "Phone", "LinkedIn",
    "Verified", "Email Valid", "Data Source",
    "Status", "Batch ID",
]


def _get_client():
    global _client
    if _client is not None:
        return _client
    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not creds_file or not Path(creds_file).exists():
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        _client = gspread.authorize(creds)
        return _client
    except Exception:
        return None


def _get_sheet(sheet_id: str, worksheet_name: str = "Batch Results"):
    key = f"{sheet_id}:{worksheet_name}"
    if key in _sheet_cache:
        return _sheet_cache[key]
    client = _get_client()
    if not client:
        return None
    try:
        wb = client.open_by_key(sheet_id)
        try:
            ws = wb.worksheet(worksheet_name)
        except Exception:
            ws = wb.add_worksheet(title=worksheet_name, rows=5000, cols=len(HEADERS))
        # Write headers if sheet is empty
        if ws.row_count == 0 or not ws.row_values(1):
            ws.append_row(HEADERS, value_input_option="RAW")
        _sheet_cache[key] = ws
        return ws
    except Exception:
        return None


def append_results(address: str, leaders: list[dict], batch_id: str, status: str = "done") -> bool:
    """
    Append one row per person to the Google Sheet.
    Returns True if written, False if skipped (no credentials).
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        return False

    ws = _get_sheet(sheet_id)
    if not ws:
        return False

    rows = []
    if not leaders:
        rows.append([
            address, "", "", "", "", "No contacts found", "", "", "", "", "", "", "", status, batch_id
        ])
    else:
        for p in leaders:
            rows.append([
                address,
                p.get("company", ""),
                p.get("raw_entity", ""),
                p.get("owner_source", ""),
                p.get("company_confidence", ""),
                p.get("name", p.get("full_name", "")),
                p.get("title", ""),
                p.get("email", ""),
                p.get("phone", ""),
                p.get("linkedin_url", ""),
                "Yes" if p.get("verified") else "No",
                "Yes" if p.get("email_valid") else "No",
                p.get("data_source", ""),
                status,
                batch_id,
            ])

    with _lock:
        try:
            ws.append_rows(rows, value_input_option="RAW")
            return True
        except Exception:
            return False


def sheets_configured() -> bool:
    """Return True if Google Sheets credentials are set up."""
    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    return bool(creds_file and Path(creds_file).exists() and sheet_id)
