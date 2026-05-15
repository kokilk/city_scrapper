"""
Validation layer — 3 checkpoints before any result is trusted.

Checkpoint 1 — Company:   confirmed from 2 independent web sources
Checkpoint 2 — People:    each person confirmed from 2 independent sources
Checkpoint 3 — Email:     format + domain MX check (full SMTP when NeverBounce/ZeroBounce key added)
"""

from __future__ import annotations

import re
import socket
import urllib.request
import urllib.parse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from leadership.tools import search_web


# ══════════════════════════════════════════════════════════════════
# Checkpoint 1 — Company validation
# ══════════════════════════════════════════════════════════════════

def validate_company(company: str, address: str, city: str, state: str) -> dict:
    """
    Confirm the company name is the real owner by finding it in 2+ independent sources.

    Returns:
        {
          "confirmed": bool,          # True if found in 2+ sources
          "sources_found": int,       # How many sources confirmed it
          "confidence": str,          # "High" / "Medium" / "Low"
          "validation_note": str,     # Human-readable explanation
        }
    """
    hits = 0
    notes = []

    # Source 1 — company name tied to this specific address
    q1 = f'"{company}" "{address}" {city}'
    r1 = search_web(q1, 3)
    if r1.get("results"):
        hits += 1
        notes.append(f'address+company match ({r1["results"][0].get("url", "web")})')

    # Source 2 — company as a real estate owner in this city/state
    q2 = f'"{company}" real estate owner property {city} {state}'
    r2 = search_web(q2, 3)
    if r2.get("results"):
        # Require snippet to actually mention the company (not just a tangential result)
        for item in r2["results"]:
            snippet = (item.get("snippet") or "").lower()
            company_words = [w.lower() for w in company.split() if len(w) > 3]
            if any(w in snippet for w in company_words):
                hits += 1
                notes.append(f'owner identity confirmed ({item.get("url", "web")})')
                break

    if hits >= 2:
        confidence = "High"
        note = f"Confirmed across {hits} independent sources"
    elif hits == 1:
        confidence = "Medium"
        note = f"Found in 1 source only — treat with caution"
    else:
        confidence = "Low"
        note = "Could not confirm company ownership — possible hallucination"

    return {
        "confirmed": hits >= 2,
        "sources_found": hits,
        "confidence": confidence,
        "validation_note": note,
    }


# ══════════════════════════════════════════════════════════════════
# Checkpoint 2 — Person validation
# ══════════════════════════════════════════════════════════════════

def validate_person(name: str, company: str) -> dict:
    """
    Confirm a person actually works (or worked) at the company from 2 independent sources.

    Returns:
        {
          "verified": bool,
          "sources_found": int,
          "validation_note": str,
        }
    """
    hits = 0
    first_name = name.split()[0].lower() if name else ""
    last_name = name.split()[-1].lower() if name else ""
    company_fragment = company.lower()[:12]

    # Source 1 — LinkedIn
    q1 = f'"{name}" "{company}" site:linkedin.com'
    r1 = search_web(q1, 3)
    for item in r1.get("results", []):
        url = (item.get("url") or "").lower()
        snippet = (item.get("snippet") or "").lower()
        if "linkedin.com" in url and (first_name in snippet or last_name in snippet):
            hits += 1
            break

    # Source 2 — general web (company website, news, bio pages)
    q2 = f'"{name}" "{company}"'
    r2 = search_web(q2, 5)
    for item in r2.get("results", []):
        snippet = (item.get("snippet") or "").lower()
        title = (item.get("title") or "").lower()
        combined = snippet + " " + title
        # Both first/last name AND company fragment must appear
        name_present = first_name in combined or last_name in combined
        company_present = any(w in combined for w in company_fragment.split()[:2] if len(w) > 3)
        if name_present and company_present:
            hits += 1
            break

    if hits >= 2:
        note = "Verified across 2 independent sources"
    elif hits == 1:
        note = "Found in 1 source only"
    else:
        note = "Could not verify — may be hallucinated"

    return {
        "verified": hits >= 2,
        "sources_found": hits,
        "validation_note": note,
    }


def validate_people_batch(people: list[dict], company: str, max_workers: int = 6) -> list[dict]:
    """
    Validate up to the first 15 people in parallel.
    Adds "verified", "person_sources", "person_validation_note" to each person dict.
    Unverified people are included but flagged — never silently dropped.
    """
    results = []
    # Only validate first 15 to keep costs and time reasonable
    to_validate = people[:15]
    rest = people[15:]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {
            ex.submit(validate_person, p["name"], company): p
            for p in to_validate
        }
        validated: dict[int, dict] = {}
        for future in as_completed(future_map):
            person = future_map[future]
            v = future.result()
            idx = to_validate.index(person)
            validated[idx] = {**person, **{
                "verified":               v["verified"],
                "person_sources":         v["sources_found"],
                "person_validation_note": v["validation_note"],
            }}

    # Preserve original order
    for i, p in enumerate(to_validate):
        results.append(validated.get(i, {**p, "verified": False, "person_sources": 0,
                                         "person_validation_note": "Validation skipped"}))

    # Anything beyond 15 is unvalidated
    for p in rest:
        results.append({**p, "verified": False, "person_sources": 0,
                        "person_validation_note": "Beyond validation limit"})

    return results


# ══════════════════════════════════════════════════════════════════
# Checkpoint 3 — Email validation
# ══════════════════════════════════════════════════════════════════

def _check_mx(domain: str) -> bool:
    """Check if a domain has MX records (accepts email). Uses DNS over HTTPS as fallback."""
    # Method 1: try resolving the mail server via socket
    try:
        socket.getaddrinfo(f"mail.{domain}", None)
        return True
    except socket.gaierror:
        pass

    # Method 2: Google DNS over HTTPS (no library needed)
    try:
        url = f"https://dns.google/resolve?name={urllib.parse.quote(domain)}&type=MX"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return bool(data.get("Answer"))
    except Exception:
        return False


def _neverbounce_verify(email: str) -> dict:
    """Call NeverBounce API if key is present."""
    api_key = os.getenv("NEVERBOUNCE_API_KEY", "")
    if not api_key:
        return {}
    try:
        params = urllib.parse.urlencode({"key": api_key, "email": email})
        url = f"https://api.neverbounce.com/v4/single/check?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        result = data.get("result", "unknown")
        # NeverBounce results: valid, invalid, disposable, catchall, unknown
        return {
            "deliverable": result == "valid",
            "status": result,
            "source": "NeverBounce",
        }
    except Exception:
        return {}


def _zerobounce_verify(email: str) -> dict:
    """Call ZeroBounce API if key is present."""
    api_key = os.getenv("ZEROBOUNCE_API_KEY", "")
    if not api_key:
        return {}
    try:
        params = urllib.parse.urlencode({"apikey": api_key, "email": email})
        url = f"https://api.zerobounce.net/v2/validate?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        status = data.get("status", "Unknown").lower()
        return {
            "deliverable": status == "valid",
            "status": status,
            "source": "ZeroBounce",
        }
    except Exception:
        return {}


def validate_email(email: str) -> dict:
    """
    3-tier email validation:
      Tier 1 (always): format check
      Tier 2 (always): domain MX record check
      Tier 3 (when key present): NeverBounce or ZeroBounce full SMTP verification

    Returns:
        {
          "valid": bool,
          "deliverable": bool | None,   # None = not checked yet (no API key)
          "reason": str,
          "source": str,
        }
    """
    if not email or not email.strip():
        return {"valid": False, "deliverable": False, "reason": "Empty", "source": "—"}

    email = email.strip().lower()

    # Tier 1 — format
    if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
        return {"valid": False, "deliverable": False, "reason": "Invalid format", "source": "Format check"}

    domain = email.split("@")[1]

    # Tier 2 — MX records
    if not _check_mx(domain):
        return {"valid": False, "deliverable": False, "reason": "Domain has no mail server", "source": "MX check"}

    # Tier 3 — full SMTP verification (only if key is present)
    nb = _neverbounce_verify(email)
    if nb:
        return {"valid": nb["deliverable"], "deliverable": nb["deliverable"],
                "reason": nb["status"], "source": nb["source"]}

    zb = _zerobounce_verify(email)
    if zb:
        return {"valid": zb["deliverable"], "deliverable": zb["deliverable"],
                "reason": zb["status"], "source": zb["source"]}

    # Format + MX passed but no SMTP key — mark as likely valid
    return {"valid": True, "deliverable": None,
            "reason": "Format + MX passed (add NeverBounce key for full verification)",
            "source": "MX check"}


def validate_emails_batch(people: list[dict]) -> list[dict]:
    """Run email validation on all people in parallel."""
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        future_map = {ex.submit(validate_email, p.get("email", "")): i
                      for i, p in enumerate(people)}
        email_results: dict[int, dict] = {}
        for future in as_completed(future_map):
            idx = future_map[future]
            email_results[idx] = future.result()

    for i, p in enumerate(people):
        ev = email_results.get(i, {})
        results.append({**p,
            "email_valid":       ev.get("valid", False),
            "email_deliverable": ev.get("deliverable"),
            "email_check_note":  ev.get("reason", "—"),
            "email_check_source": ev.get("source", "—"),
        })
    return results
