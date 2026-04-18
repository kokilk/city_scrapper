"""
Tools — All API calls Claude can invoke as tools.

Each function is registered as a Claude tool. Claude decides which to call,
when, and with what arguments. No hardcoded pipeline order.

Tools available:
  - scrape_permits         NYC DOB permit data (free)
  - lookup_owner           NYC PLUTO property owner (free)
  - search_web             Exa.ai semantic search
  - google_search          Google Custom Search (fallback)
  - enrich_contact         Apollo.io — LinkedIn, email, phone by name+company
  - find_email             Hunter.io — email by company domain
  - lookup_company         OpenCorporates — LLC officers (free 200/mo)
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv
load_dotenv()

# ── HTTP helpers ──────────────────────────────────────────────────────────────

# Cloudflare blocks requests without a real browser User-Agent
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _get(url: str, timeout: int = 15) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _post(url: str, headers: dict, payload: dict, timeout: int = 15) -> dict:
    data = json.dumps(payload).encode()
    headers.setdefault("User-Agent", _UA)
    headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


# ── Tool implementations ───────────────────────────────────────────────────────

def scrape_permits(address: str, city: str, state: str) -> dict:
    """
    Fetch building permits for an address from free public city APIs.
    Currently supports NYC. Returns permit applicants, owners, contractors.
    """
    city_upper = city.upper().strip()
    nyc_cities = {"NEW YORK", "MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND"}

    if city_upper not in nyc_cities and state.upper() != "NY":
        return {
            "permits": [],
            "message": f"No free permit API available for {city}, {state}. Web search recommended.",
        }

    # Parse house number and street
    parts = address.strip().split()
    house = parts[0] if parts and parts[0].rstrip("-").isdigit() else ""
    street_parts = parts[1:] if house else parts
    # Strip unit suffixes
    clean_parts = []
    for p in street_parts:
        if p.upper() in ("STE", "APT", "UNIT", "FL", "FLOOR", "#"):
            break
        clean_parts.append(p)
    street = " ".join(clean_parts).upper()

    borough_map = {
        "MANHATTAN": "MANHATTAN", "NEW YORK": "MANHATTAN",
        "BROOKLYN": "BROOKLYN", "QUEENS": "QUEENS",
        "BRONX": "BRONX", "STATEN ISLAND": "STATEN ISLAND",
    }
    borough = borough_map.get(city_upper, "MANHATTAN")

    params = urllib.parse.urlencode({
        "$where": f"upper(street_name) like '%{street}%' AND upper(borough) = '{borough}'",
        "$limit": "50",
        "$order": "latest_action_date DESC",
    })
    url = f"https://data.cityofnewyork.us/resource/ic3t-wcy2.json?{params}"

    raw = _get(url)
    if isinstance(raw, dict) and "error" in raw:
        return {"permits": [], "error": raw["error"]}

    # Filter by house number
    results = raw if isinstance(raw, list) else []
    if house:
        matched = [r for r in results if str(r.get("house__", "")).strip() == house]
        if matched:
            results = matched

    job_type_map = {
        "NB": "New Building", "A1": "Major Alteration", "A2": "Minor Alteration",
        "A3": "Minor Alteration", "DM": "Demolition", "SG": "Sign",
    }

    permits = []
    seen = set()
    for r in results[:10]:  # cap at 10 to reduce tokens
        applicant = " ".join(filter(None, [
            r.get("applicant_s_first_name", ""),
            r.get("applicant_s_last_name", ""),
        ])).strip()
        owner = (
            r.get("owner_s_business_name", "")
            or " ".join(filter(None, [
                r.get("owner_s_first_name", ""),
                r.get("owner_s_last_name", ""),
            ])).strip()
        )
        contractor = r.get("contractor_s_business_name", "")
        key = (applicant, owner, contractor)
        if key in seen:
            continue
        seen.add(key)
        permits.append({
            "permit_id": r.get("job__", ""),
            "permit_type": job_type_map.get(r.get("job_type", "").upper(), r.get("job_type", "")),
            "file_date": r.get("pre__filing_date", r.get("latest_action_date", ""))[:10],
            "job_value": r.get("initial_cost", ""),
            "applicant_name": applicant,
            "applicant_title": r.get("applicant_professional_title", ""),
            "owner_name": owner,
            "contractor_name": contractor,
        })

    return {"permits": permits, "count": len(permits), "source": "NYC_DOB"}


def lookup_owner(address: str, city: str) -> dict:
    """
    Look up property owner from NYC PLUTO dataset (free, no API key).
    Returns owner name, building class, year built, assessed value.
    """
    city_upper = city.upper().strip()
    nyc_cities = {"NEW YORK", "MANHATTAN", "BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND"}
    if city_upper not in nyc_cities:
        return {"owner_name": "", "message": f"PLUTO only available for NYC, not {city}"}

    borough_map = {
        "MANHATTAN": "MN", "NEW YORK": "MN", "BROOKLYN": "BK",
        "QUEENS": "QN", "BRONX": "BX", "STATEN ISLAND": "SI",
    }
    borough = borough_map.get(city_upper, "MN")

    parts = address.strip().upper().split()
    house = parts[0] if parts and parts[0].rstrip("-").isdigit() else ""
    street = " ".join(parts[1:]) if house else " ".join(parts)

    params = urllib.parse.urlencode({
        "$where": f"upper(address) like '%{street}%' AND borough = '{borough}'",
        "$limit": "5",
    })
    url = f"https://data.cityofnewyork.us/resource/64uk-42ks.json?{params}"

    raw = _get(url)
    if isinstance(raw, dict) and "error" in raw:
        return {"owner_name": "", "error": raw["error"]}

    results = raw if isinstance(raw, list) else []
    if house and results:
        matched = [r for r in results if r.get("address", "").startswith(house)]
        if matched:
            results = matched

    if not results:
        return {"owner_name": "", "message": "No PLUTO record found"}

    r = results[0]
    return {
        "owner_name": r.get("ownername", ""),
        "building_class": r.get("bldgclass", ""),
        "year_built": r.get("yearbuilt", ""),
        "assessed_value": r.get("assesstot", ""),
        "num_floors": r.get("numfloors", ""),
        "borough": r.get("borough", ""),
        "block": r.get("block", ""),
        "lot": r.get("lot", ""),
        "source": "NYC_PLUTO",
    }


def search_web(query: str, num_results: int = 5) -> dict:
    """
    Search the web using Exa.ai for a person or company.
    Best for finding company websites, contact info, news mentions.
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return {"results": [], "error": "EXA_API_KEY not set"}

    payload = {
        "query": query,
        "numResults": min(num_results, 5),
        "useAutoprompt": True,
        "type": "neural",
        "contents": {"text": {"maxCharacters": 400}},
    }
    headers = {"Content-Type": "application/json", "x-api-key": api_key}
    data = _post("https://api.exa.ai/search", headers, payload)

    if "error" in data:
        return {"results": [], "error": data["error"]}

    results = []
    for r in data.get("results", []):
        text = r.get("text") or r.get("snippet") or ""
        results.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": text[:500],
        })
    return {"results": results, "query": query}


def google_search(query: str, num_results: int = 5) -> dict:
    """
    Search using Google Custom Search API.
    Good fallback for business info, contact pages, LinkedIn profiles.
    """
    api_key = os.getenv("GOOGLE_CSE_API_KEY", "")
    cx = os.getenv("GOOGLE_CSE_ID", "")
    if not api_key or not cx:
        return {"results": [], "error": "GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not set"}

    params = urllib.parse.urlencode({
        "key": api_key, "cx": cx,
        "q": query, "num": min(num_results, 10),
    })
    data = _get(f"https://www.googleapis.com/customsearch/v1?{params}")

    if isinstance(data, dict) and "error" in data:
        return {"results": [], "error": str(data.get("error", ""))}

    results = []
    for item in data.get("items", []):  # type: ignore[union-attr]
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
        })
    return {"results": results, "query": query}


def enrich_contact(name: str, company: str, find_phone: bool = False) -> dict:
    """
    Find LinkedIn URL and profile details for a person using Exa.ai.
    Searches for personal LinkedIn profiles and fetches headline, location, summary.
    """
    exa_key = os.getenv("EXA_API_KEY", "")
    if not exa_key:
        return {"found": False, "error": "EXA_API_KEY not set"}

    headers = {"Content-Type": "application/json", "x-api-key": exa_key}
    linkedin_url = ""
    headline = ""
    location = ""
    summary = ""

    # Strategy 1: search linkedin.com/in/ with name + company
    for query in [
        f'"{name}" "{company}" linkedin',
        f'"{name}" linkedin site:linkedin.com/in',
        f"{name} {company} linkedin profile",
    ]:
        payload = {
            "query": query,
            "numResults": 5,
            "useAutoprompt": False,
            "type": "neural",
            "includeDomains": ["linkedin.com"],
            "contents": {"text": {"maxCharacters": 600}},
        }
        data = _post("https://api.exa.ai/search", headers, payload)
        if data.get("error"):
            continue
        for r in data.get("results", []):
            url = r.get("url", "")
            if "linkedin.com/in/" in url:
                linkedin_url = url
                text = r.get("text", "") or r.get("snippet", "")
                # Extract headline and location from profile text
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if lines:
                    headline = lines[0][:120]
                if len(lines) > 1:
                    summary = " ".join(lines[1:4])[:300]
                break
        if linkedin_url:
            break

    # Strategy 2: if no URL found, try fetching profile content directly
    if not linkedin_url:
        # Build a likely LinkedIn slug and verify via Exa
        slug = name.lower().replace(" ", "-").replace(".", "")
        candidate = f"https://www.linkedin.com/in/{slug}"
        verify_payload = {
            "ids": [candidate],
            "contents": {"text": {"maxCharacters": 400}},
        }
        verify_data = _post("https://api.exa.ai/contents", headers, verify_payload)
        for r in verify_data.get("results", []):
            text = r.get("text", "")
            # Check if the name appears in the profile text
            if name.split()[0].lower() in text.lower() and name.split()[-1].lower() in text.lower():
                linkedin_url = candidate
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if lines:
                    headline = lines[0][:120]
                break

    return {
        "found": bool(linkedin_url),
        "linkedin_url": linkedin_url,
        "headline": headline,
        "location": location,
        "summary": summary,
        "email": "",
        "phone": "",
        "source": "Exa",
    }


def find_email(name: str, domain: str) -> dict:
    """
    Find email address for a person at a company using Hunter.io.
    Use when Apollo doesn't return an email and you have the company domain.
    """
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key:
        return {"error": "HUNTER_API_KEY not set"}

    # Try name-based search first
    parts = name.strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""

    if first and last:
        params = urllib.parse.urlencode({
            "domain": domain, "first_name": first,
            "last_name": last, "api_key": api_key,
        })
        data = _get(f"https://api.hunter.io/v2/email-finder?{params}")
        if isinstance(data, dict):
            email = data.get("data", {}).get("email", "")
            if email:
                return {
                    "email": email,
                    "confidence": data.get("data", {}).get("score", 0),
                    "source": "Hunter",
                }

    # Fall back to domain search
    params = urllib.parse.urlencode({"domain": domain, "api_key": api_key, "limit": "5"})
    data = _get(f"https://api.hunter.io/v2/domain-search?{params}")
    if isinstance(data, dict):
        emails = data.get("data", {}).get("emails", [])
        if emails:
            return {
                "email": emails[0].get("value", ""),
                "confidence": emails[0].get("confidence", 0),
                "source": "Hunter",
            }

    return {"email": "", "message": "No email found"}


def lookup_company(company_name: str, state: str = "") -> dict:
    """
    Look up LLC/corporation officers by searching the web for the company's
    principals, managing members, and registered agents.
    Uses Exa web search to find SEC filings, news, and company pages.
    """
    exa_key = os.getenv("EXA_API_KEY", "")
    if not exa_key:
        return {"officers": [], "error": "EXA_API_KEY not set"}

    state_str = f"{state} " if state else ""
    query = f'"{company_name}" {state_str}LLC managing member principal officer registered agent'

    payload = {
        "query": query,
        "numResults": 5,
        "useAutoprompt": True,
        "type": "neural",
        "contents": {"text": {"maxCharacters": 600}},
    }
    headers = {"Content-Type": "application/json", "x-api-key": exa_key}
    data = _post("https://api.exa.ai/search", headers, payload)

    if data.get("error"):
        return {"officers": [], "error": data["error"]}

    results = []
    for r in data.get("results", []):
        results.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("text", "")[:400],
        })

    return {
        "company_name": company_name,
        "search_results": results,
        "note": "Parse these results to identify managing members, principals, and officers",
        "source": "Exa",
    }


# ── Tool definitions for Claude API ───────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "scrape_permits",
        "description": (
            "Fetch building permits for a property address from free public city APIs. "
            "Returns permit applicants (often Developer/Architect), owner name, and contractor. "
            "Currently supports NYC. Use this first for any address."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Street address e.g. '350 5th Ave'"},
                "city": {"type": "string", "description": "City name e.g. 'Manhattan', 'Brooklyn'"},
                "state": {"type": "string", "description": "2-letter state code e.g. 'NY'"},
            },
            "required": ["address", "city", "state"],
        },
    },
    {
        "name": "lookup_owner",
        "description": (
            "Look up property owner from NYC PLUTO dataset (free, no API key needed). "
            "Returns owner name, building class, year built, assessed value. NYC only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Street address e.g. '350 5th Ave'"},
                "city": {"type": "string", "description": "NYC borough or 'New York'"},
            },
            "required": ["address", "city"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web using Exa.ai. Best for finding company websites, "
            "contact info, news mentions, and verifying stakeholder roles. "
            "Use targeted queries like 'John Smith architect NYC contact email'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results (1-10)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "google_search",
        "description": (
            "Search using Google Custom Search. Use as fallback when Exa returns poor results, "
            "or specifically to find LinkedIn profiles and official company pages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results (1-10)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "enrich_contact",
        "description": (
            "Find LinkedIn URL for a person by searching Exa for their LinkedIn profile. "
            "Use after you have a person's name and company from permit or owner data. "
            "For email, use find_email() separately with the company domain."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's full name"},
                "company": {"type": "string", "description": "Company name"},
                "find_phone": {"type": "boolean", "description": "Unused — kept for compatibility", "default": False},
            },
            "required": ["name", "company"],
        },
    },
    {
        "name": "find_email",
        "description": (
            "Find a person's email at a company using Hunter.io domain search. "
            "Use when Apollo doesn't return an email and you know the company domain."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's full name"},
                "domain": {"type": "string", "description": "Company domain e.g. 'smitharchitects.com'"},
            },
            "required": ["name", "domain"],
        },
    },
    {
        "name": "lookup_company",
        "description": (
            "Search the web to find the principals, managing members, and officers of an LLC or company. "
            "Use to pierce shell companies and find the human decision-makers behind them. "
            "Returns web search results mentioning the company's officers and principals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company or LLC name"},
                "state": {"type": "string", "description": "2-letter state code (optional but improves accuracy)"},
            },
            "required": ["company_name"],
        },
    },
]

# ── Tool dispatcher — called by agent.py ─────────────────────────────────────

TOOL_MAP = {
    "scrape_permits": scrape_permits,
    "lookup_owner": lookup_owner,
    "search_web": search_web,
    "google_search": google_search,
    "enrich_contact": enrich_contact,
    "find_email": find_email,
    "lookup_company": lookup_company,
}


def call_tool(name: str, inputs: dict) -> str:
    """Dispatch a tool call and return result as JSON string."""
    fn = TOOL_MAP.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**inputs)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": f"Tool {name} failed: {e}"})
