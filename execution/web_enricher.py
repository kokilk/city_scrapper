"""
Web Enricher — Find website, email, phone for stakeholders via Exa + Google CSE

For each stakeholder candidate (name + company), searches:
  1. Exa.ai   — semantic web search, best for finding company pages
  2. Google Custom Search (CSE) — fallback / second opinion

Extracts from search results:
  - Company website URL
  - Email address (regex from page snippets)
  - Phone number (regex from page snippets)
  - LinkedIn profile URL

Input:  .tmp/stakeholder_candidates.json
Output: .tmp/web_enriched.json  (adds website, phone, email fields to each candidate)

API keys required (in .env):
  EXA_API_KEY
  GOOGLE_CSE_API_KEY
  GOOGLE_CSE_ID
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).parent.parent
TMP = BASE / ".tmp"
INPUT_PATH = TMP / "stakeholder_candidates.json"
OUTPUT_PATH = TMP / "web_enriched.json"

EXA_SEARCH_URL = "https://api.exa.ai/search"
GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

# Regex patterns for extracting contact info from text snippets
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+1[\s\-.]?)?"
    r"(?:\(?\d{3}\)?[\s\-.]?)"
    r"\d{3}[\s\-.]?\d{4}"
)
_LINKEDIN_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/(?:in|company)/[a-zA-Z0-9\-_%]+/?",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def _post_json(url: str, headers: dict, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        print(f"[web_enricher] POST error {url}: {exc}", file=sys.stderr)
        return {}


def _get_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        print(f"[web_enricher] GET error {url}: {exc}", file=sys.stderr)
        return {}


def _build_query(name: str, company: str, role: str) -> str:
    """Build a targeted search query for a stakeholder."""
    parts = [p for p in [name, company, role, "contact", "phone", "email"] if p]
    return " ".join(parts[:5])


def _extract_from_text(text: str) -> dict[str, str]:
    """Pull email, phone, LinkedIn from a text snippet."""
    result: dict[str, str] = {}

    emails = _EMAIL_RE.findall(text)
    # Filter out generic/noreply emails
    real_emails = [
        e for e in emails
        if not any(x in e.lower() for x in ["noreply", "no-reply", "example.com", "test@"])
    ]
    if real_emails:
        result["email"] = real_emails[0]

    phones = _PHONE_RE.findall(text)
    if phones:
        # Clean up and format
        raw = re.sub(r"[^\d+]", "", phones[0])
        if len(raw) == 10:
            result["phone"] = f"+1{raw}"
        elif len(raw) == 11 and raw.startswith("1"):
            result["phone"] = f"+{raw}"
        else:
            result["phone"] = phones[0].strip()

    linkedins = _LINKEDIN_RE.findall(text)
    if linkedins:
        result["linkedin_url"] = linkedins[0]

    return result


def _best_website_from_urls(urls: list[str], company: str) -> str:
    """Pick the most relevant URL as the company website."""
    company_words = set(re.sub(r"[^a-z0-9]", " ", company.lower()).split())
    company_words.discard("llc")
    company_words.discard("inc")
    company_words.discard("corp")
    company_words.discard("the")

    # Prefer URLs that contain company name words
    scored: list[tuple[int, str]] = []
    for url in urls:
        domain = url.lower()
        score = sum(1 for w in company_words if len(w) > 3 and w in domain)
        # Prefer root domains (fewer path segments = more likely homepage)
        path_depth = url.count("/") - 2
        scored.append((score * 10 - path_depth, url))

    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0:
        return scored[0][1]
    return urls[0] if urls else ""


def _exa_search(name: str, company: str, role: str, api_key: str) -> dict[str, str]:
    """Search Exa.ai and extract contact info."""
    query = _build_query(name, company, role)
    payload = {
        "query": query,
        "numResults": 5,
        "useAutoprompt": True,
        "type": "neural",
        "contents": {
            "text": {"maxCharacters": 800},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }

    data = _post_json(EXA_SEARCH_URL, headers, payload)
    results = data.get("results", [])

    if not results:
        return {}

    all_text = " ".join(
        (r.get("text") or r.get("snippet") or r.get("title") or "")
        for r in results
    )
    all_urls = [r.get("url", "") for r in results if r.get("url")]

    extracted = _extract_from_text(all_text)

    # Pick best website
    website = _best_website_from_urls(all_urls, company or name)
    if website:
        extracted["website"] = website

    return extracted


def _google_cse_search(name: str, company: str, role: str, api_key: str, cx: str) -> dict[str, str]:
    """Search Google CSE and extract contact info."""
    query = _build_query(name, company, role)
    params = urllib.parse.urlencode({
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": 5,
    })
    url = f"{GOOGLE_CSE_URL}?{params}"
    data = _get_json(url)

    items = data.get("items", [])
    if not items:
        return {}

    all_text = " ".join(
        (item.get("snippet", "") + " " + item.get("title", ""))
        for item in items
    )
    all_urls = [item.get("link", "") for item in items if item.get("link")]

    extracted = _extract_from_text(all_text)

    website = _best_website_from_urls(all_urls, company or name)
    if website:
        extracted.setdefault("website", website)

    return extracted


def enrich_one(candidate: dict[str, Any], exa_key: str, cse_key: str, cse_id: str) -> dict[str, Any]:
    """Enrich a single candidate with web search results."""
    name = candidate.get("raw_name", "")
    company = candidate.get("company", "")
    role = candidate.get("role", "")

    if not name and not company:
        return dict(candidate)

    print(f"[web_enricher] Searching: {name} / {company} ({role})")

    merged: dict[str, str] = {}

    # Try Exa first
    if exa_key:
        exa_result = _exa_search(name, company, role, exa_key)
        merged.update(exa_result)

    # Fill gaps with Google CSE
    if cse_key and cse_id:
        missing = not merged.get("email") or not merged.get("website")
        if missing:
            cse_result = _google_cse_search(name, company, role, cse_key, cse_id)
            for field in ("email", "phone", "website", "linkedin_url"):
                if not merged.get(field) and cse_result.get(field):
                    merged[field] = cse_result[field]

    enriched = dict(candidate)
    enriched["website"] = merged.get("website", "")

    # Only set email/phone/linkedin if not already present from permit data
    if not enriched.get("email"):
        enriched["email"] = merged.get("email", "")
    if not enriched.get("phone"):
        enriched["phone"] = merged.get("phone", "")
    if not enriched.get("linkedin_url"):
        enriched["linkedin_url"] = merged.get("linkedin_url", "")

    web_sources = []
    if exa_key and merged:
        web_sources.append("Exa")
    if cse_key and cse_id and merged:
        web_sources.append("GoogleCSE")
    enriched.setdefault("enrichment_sources", [])
    enriched["enrichment_sources"] = list(enriched["enrichment_sources"]) + web_sources

    return enriched


def enrich_all(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exa_key = os.getenv("EXA_API_KEY", "")
    cse_key = os.getenv("GOOGLE_CSE_API_KEY", "")
    cse_id = os.getenv("GOOGLE_CSE_ID", "")

    if not exa_key and not (cse_key and cse_id):
        print("[web_enricher] WARNING: No Exa or Google CSE keys — skipping web enrichment", file=sys.stderr)
        return candidates

    return [enrich_one(c, exa_key, cse_key, cse_id) for c in candidates]


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[web_enricher] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    candidates = json.loads(INPUT_PATH.read_text())
    print(f"[web_enricher] Web-enriching {len(candidates)} candidate(s)…")

    enriched = enrich_all(candidates)
    OUTPUT_PATH.write_text(json.dumps(enriched, indent=2, default=str))

    with_website = sum(1 for c in enriched if c.get("website"))
    with_email = sum(1 for c in enriched if c.get("email"))
    with_phone = sum(1 for c in enriched if c.get("phone"))
    print(
        f"[web_enricher] Done: {with_website} websites, "
        f"{with_email} emails, {with_phone} phones → {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
