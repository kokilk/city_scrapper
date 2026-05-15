"""
Central API configuration — reads from .env and exposes availability flags.

To add a new API:
  1. Add the key to config/api_keys.env.example (with instructions)
  2. Add the key to your .env file
  3. Add a flag below so the pipeline can check if it's available
  4. Wire the API call into leadership/tools.py
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

def _key(name: str) -> str:
    return os.getenv(name, "").strip()

def _has(name: str) -> bool:
    return bool(_key(name))


# ── Core AI ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = _key("ANTHROPIC_API_KEY")

# ── Property Data ─────────────────────────────────────────────────────────────
REGRID_API_KEY      = _key("REGRID_API_KEY")
BATCHDATA_API_KEY   = _key("BATCHDATA_API_KEY")
REONOMY_API_KEY     = _key("REONOMY_API_KEY")

# ── Contact Enrichment ────────────────────────────────────────────────────────
APOLLO_API_KEY      = _key("APOLLO_API_KEY")
PDL_API_KEY         = _key("PDL_API_KEY")
LUSHA_API_KEY       = _key("LUSHA_API_KEY")
HUNTER_API_KEY      = _key("HUNTER_API_KEY")
PROXYCURL_API_KEY   = _key("PROXYCURL_API_KEY")
APIFY_API_KEY       = _key("APIFY_API_KEY")

# ── Web Search ────────────────────────────────────────────────────────────────
EXA_API_KEY         = _key("EXA_API_KEY")
GOOGLE_CSE_API_KEY  = _key("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_ID       = _key("GOOGLE_CSE_ID")

# ── Email Validation ──────────────────────────────────────────────────────────
NEVERBOUNCE_API_KEY = _key("NEVERBOUNCE_API_KEY")
ZEROBOUNCE_API_KEY  = _key("ZEROBOUNCE_API_KEY")

# ── Address Validation ────────────────────────────────────────────────────────
SMARTY_AUTH_ID      = _key("SMARTY_AUTH_ID")
SMARTY_AUTH_TOKEN   = _key("SMARTY_AUTH_TOKEN")

# ── Outputs ───────────────────────────────────────────────────────────────────
GOOGLE_SHEET_ID     = _key("GOOGLE_SHEET_ID")


# ── Availability flags (use these in the pipeline) ────────────────────────────
HAS_REGRID          = _has("REGRID_API_KEY")
HAS_BATCHDATA       = _has("BATCHDATA_API_KEY")
HAS_REONOMY         = _has("REONOMY_API_KEY")
HAS_APOLLO          = _has("APOLLO_API_KEY")
HAS_PDL             = _has("PDL_API_KEY")
HAS_LUSHA           = _has("LUSHA_API_KEY")
HAS_HUNTER          = _has("HUNTER_API_KEY")
HAS_PROXYCURL       = _has("PROXYCURL_API_KEY")
HAS_APIFY           = _has("APIFY_API_KEY")
HAS_EXA             = _has("EXA_API_KEY")
HAS_NEVERBOUNCE     = _has("NEVERBOUNCE_API_KEY")
HAS_ZEROBOUNCE      = _has("ZEROBOUNCE_API_KEY")


def status() -> dict:
    """Return a dict showing which APIs are configured. Useful for debugging."""
    return {
        "property": {
            "Regrid":    HAS_REGRID,
            "BatchData": HAS_BATCHDATA,
            "Reonomy":   HAS_REONOMY,
        },
        "contacts": {
            "Apollo":    HAS_APOLLO,
            "PDL":       HAS_PDL,
            "Lusha":     HAS_LUSHA,
            "Hunter":    HAS_HUNTER,
            "Proxycurl": HAS_PROXYCURL,
            "Apify":     HAS_APIFY,
        },
        "search": {
            "Exa":       HAS_EXA,
            "Google":    _has("GOOGLE_CSE_API_KEY"),
        },
        "validation": {
            "NeverBounce": HAS_NEVERBOUNCE,
            "ZeroBounce":  HAS_ZEROBOUNCE,
        },
    }
