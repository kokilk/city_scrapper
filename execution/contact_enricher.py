"""
Stage 3b: Contact Enrichment (Apollo + Hunter)

Runs AFTER web_enricher.py. Reads web_enriched.json and fills any remaining
gaps using Apollo.io (LinkedIn URL, email) and Hunter.io (email by domain).

Strategy:
  1. If web_enricher already found email + linkedin → skip Apollo to save credits
  2. Apollo /v1/people/match → LinkedIn URL (primary goal), email, phone
  3. If no email yet → Hunter domain search by company website domain
  4. Phone enrichment (5 Apollo credits each) only for ENRICH_PHONE_ROLES

Input:  .tmp/web_enriched.json   (output of web_enricher.py)
Output: .tmp/enriched_stakeholders.json

Rate limits enforced by asyncio.Semaphore:
  Apollo:  3 concurrent
  Hunter:  5 concurrent
"""

from __future__ import annotations

import asyncio
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
from models import EnrichedStakeholder, SourceReference
from api_client import api_session, post_json, get_json, APOLLO_SEM, HUNTER_SEM

load_dotenv()

INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "web_enriched.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "enriched_stakeholders.json"

APOLLO_URL = "https://api.apollo.io/v1/people/match"
HUNTER_URL = "https://api.hunter.io/v2/domain-search"

_PHONE_ROLES = set(
    os.getenv("ENRICH_PHONE_ROLES", "Developer,GC").split(",")
)

# Simple regex to extract domain from website or email
_DOMAIN_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})")
_EMAIL_DOMAIN_RE = re.compile(r"@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")


def _extract_domain(website: str) -> str | None:
    m = _DOMAIN_RE.search(website)
    return m.group(1) if m else None


def _extract_email_domain(email: str) -> str | None:
    m = _EMAIL_DOMAIN_RE.search(email)
    return m.group(1) if m else None


def _already_enriched(candidate: dict[str, Any]) -> bool:
    """Skip Apollo if web_enricher already found both email and linkedin."""
    email = candidate.get("email", "")
    linkedin = candidate.get("linkedin_url", "")
    return bool(email and linkedin)


async def _apollo_enrich(
    session: Any,
    candidate: dict[str, Any],
    api_key: str,
    enrich_phone: bool,
) -> tuple[str, str, str, int, list[str]]:
    """Returns (email, phone, linkedin_url, confidence, sources)"""
    name = candidate.get("raw_name", "")
    company = candidate.get("company", "") or name

    payload: dict[str, Any] = {
        "name": name,
        "organization_name": company,
        "reveal_personal_emails": True,
    }
    if enrich_phone:
        payload["reveal_phone_number"] = True

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    try:
        data = await post_json(
            session,
            APOLLO_URL,
            headers=headers,
            payload=payload,
            sem=APOLLO_SEM,
        )
        person = data.get("person") or {}  # type: ignore[union-attr]
        if not person:
            return "", "", "", 0, []

        email = person.get("email", "") or ""
        phone = ""
        if enrich_phone:
            phone = person.get("phone_numbers", [{}])[0].get("sanitized_number", "") if person.get("phone_numbers") else ""
        linkedin = person.get("linkedin_url", "") or ""
        confidence = int(person.get("email_status", {}).get("score", 0) if isinstance(person.get("email_status"), dict) else 70)

        return email, phone, linkedin, confidence, ["Apollo"]

    except Exception as exc:
        print(f"[contact_enricher] Apollo error for '{name}': {exc}", file=sys.stderr)
        return "", "", "", 0, []


async def _hunter_enrich(
    session: Any,
    company: str,
    api_key: str,
    name: str,
) -> tuple[str, int, list[str]]:
    """Returns (email, confidence, sources)"""
    domain = _extract_domain(company)
    if not domain:
        return "", 0, []

    params = {
        "domain": domain,
        "api_key": api_key,
        "limit": "10",
    }

    try:
        data = await get_json(
            session,
            HUNTER_URL,
            params=params,
            sem=HUNTER_SEM,
        )
        emails_data = data.get("data", {}).get("emails", [])  # type: ignore[union-attr]
        if not emails_data:
            return "", 0, []

        # Try to match by name first
        name_lower = name.lower()
        name_parts = name_lower.split()
        for entry in emails_data:
            first = (entry.get("first_name") or "").lower()
            last = (entry.get("last_name") or "").lower()
            if any(part in (first, last) for part in name_parts if len(part) > 2):
                return entry.get("value", ""), entry.get("confidence", 50), ["Hunter"]

        # Fall back to first personal email
        personal = [e for e in emails_data if e.get("type") == "personal"]
        if personal:
            return personal[0].get("value", ""), personal[0].get("confidence", 50), ["Hunter"]

        return "", 0, []

    except Exception as exc:
        print(f"[contact_enricher] Hunter error for domain of '{company}': {exc}", file=sys.stderr)
        return "", 0, []


async def enrich_one(
    session: Any,
    candidate: dict[str, Any],
    apollo_key: str,
    hunter_key: str,
) -> dict[str, Any]:
    """Enrich a single candidate and return an EnrichedStakeholder dict."""
    if _already_enriched(candidate):
        enriched = dict(candidate)
        if "enrichment_sources" not in enriched:
            enriched["enrichment_sources"] = []
        return enriched

    role = candidate.get("role", "Unknown")
    enrich_phone = role in _PHONE_ROLES
    name = candidate.get("raw_name", "")
    company = candidate.get("company", "") or name

    email, phone, linkedin, confidence, sources = "", "", "", 0, []

    if apollo_key:
        email, phone, linkedin, confidence, sources = await _apollo_enrich(
            session, candidate, apollo_key, enrich_phone
        )

    # If Apollo returned no email, try Hunter
    if not email and hunter_key:
        h_email, h_conf, h_sources = await _hunter_enrich(session, company, hunter_key, name)
        if h_email:
            email = h_email
            confidence = h_conf
            sources = h_sources

    enriched = dict(candidate)
    enriched["email"] = email
    enriched["phone"] = phone
    enriched["linkedin_url"] = linkedin
    enriched["email_confidence"] = confidence
    enriched["enrichment_sources"] = sources
    return enriched


async def enrich_all(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    apollo_key = os.getenv("APOLLO_API_KEY", "")
    hunter_key = os.getenv("HUNTER_API_KEY", "")

    if not apollo_key and not hunter_key:
        print("[contact_enricher] WARNING: No Apollo or Hunter API keys — skipping enrichment", file=sys.stderr)
        return candidates

    enriched = []
    async with api_session() as session:
        tasks = [
            enrich_one(session, candidate, apollo_key, hunter_key)
            for candidate in candidates
        ]
        enriched = list(await asyncio.gather(*tasks))

    return enriched


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[contact_enricher] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    candidates = json.loads(INPUT_PATH.read_text())
    print(f"[contact_enricher] Enriching {len(candidates)} candidate(s)…")

    enriched = asyncio.run(enrich_all(candidates))

    OUTPUT_PATH.write_text(json.dumps(enriched, indent=2, default=str))

    with_email = sum(1 for c in enriched if c.get("email"))
    with_phone = sum(1 for c in enriched if c.get("phone"))
    print(
        f"[contact_enricher] Done: {with_email}/{len(enriched)} emails, "
        f"{with_phone}/{len(enriched)} phones → {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
