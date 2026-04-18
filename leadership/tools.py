"""
Leadership Intelligence Tools

Tools Claude can call to:
  1. Identify the company/corp that owns a building (PLUTO + permits)
  2. Find the company website and scrape its leadership/team pages
  3. Apollo.io — email + phone + verified LinkedIn in one call (PRIMARY enrichment)
  4. find_linkedin_url — validated Exa search (fallback if Apollo misses someone)
  5. Apify actor 2SyF0bVxmgGr8IVCZ — deep LinkedIn profile scrape
  6. Hunter.io — email fallback when Apollo has no result
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv
load_dotenv()

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

APIFY_ACTOR_ID = "2SyF0bVxmgGr8IVCZ"
APIFY_BASE = "https://api.apify.com/v2"


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 20) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _post(url: str, headers: dict, payload: dict, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode()
    headers.setdefault("User-Agent", _UA)
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _fetch_html(url: str, timeout: int = 15) -> str:
    """Fetch raw HTML from a URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            charset = "utf-8"
            ct = r.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            if m:
                charset = m.group(1)
            return raw.decode(charset, errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    # Remove scripts and styles completely
    html = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    # Remove tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common HTML entities
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')]:
        html = html.replace(ent, ch)
    # Collapse whitespace
    return re.sub(r"\s{2,}", " ", html).strip()


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract href links from HTML, resolve relative URLs."""
    parsed = urllib.parse.urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    hrefs = re.findall(r'href=["\']([^"\'#?]+)', html)
    links = []
    for h in hrefs:
        if h.startswith("http"):
            links.append(h)
        elif h.startswith("/"):
            links.append(base + h)
    return links


# ── Tool implementations ───────────────────────────────────────────────────────

def lookup_owner_company(address: str, city: str) -> dict:
    """
    Look up property owner from NYC PLUTO dataset.
    Returns the owning company/entity name, borough, block, lot.
    """
    city_upper = city.upper().strip()
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


def search_web(query: str, num_results: int = 5, text_chars: int = 600) -> dict:
    """
    Search the web using Exa.ai.
    Use for: company website, LinkedIn company page, leadership team mentions,
    news articles naming executives, press releases.
    text_chars: max characters per result snippet (default 600, use 1200+ for
    leadership enrichment where longer snippets capture more names).
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return {"results": [], "error": "EXA_API_KEY not set"}

    payload = {
        "query": query,
        "numResults": min(num_results, 10),
        "useAutoprompt": True,
        "type": "neural",
        "contents": {"text": {"maxCharacters": text_chars}},
    }
    headers = {"x-api-key": api_key}
    data = _post("https://api.exa.ai/search", headers, payload)

    if "error" in data:
        return {"results": [], "error": data["error"]}

    results = []
    for r in data.get("results", []):
        results.append({
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": (r.get("text") or r.get("snippet") or "")[:text_chars],
        })
    return {"results": results, "query": query}


def fetch_webpage(url: str) -> dict:
    """
    Fetch and return the text content of a webpage.
    Also returns any links that look like team/leadership/about/people pages.
    Use on company websites to find their leadership page content.
    """
    html = _fetch_html(url)
    if html.startswith("ERROR:"):
        return {"url": url, "text": "", "error": html, "leadership_links": []}

    text = _strip_html(html)[:8000]

    # Find links that might be leadership/team pages
    all_links = _extract_links(html, url)
    keywords = ("team", "leadership", "about", "people", "management",
                 "executives", "staff", "directors", "board", "principals")
    leadership_links = [
        lnk for lnk in all_links
        if any(kw in lnk.lower() for kw in keywords)
    ][:10]

    # Extract direct LinkedIn profile links from the page (most reliable source)
    linkedin_profiles = list(dict.fromkeys(
        _normalize_linkedin_url(lnk)
        for lnk in re.findall(r'https?://(?:www\.|[a-z]{2}\.)?linkedin\.com/in/[^\s"\'<>/?#]+', html)
    ))

    return {
        "url": url,
        "text": text,
        "leadership_links": list(dict.fromkeys(leadership_links)),
        "linkedin_profiles_on_page": linkedin_profiles,  # direct LinkedIn URLs found in HTML
        "char_count": len(text),
    }


def _normalize_linkedin_url(url: str) -> str:
    """Normalize any linkedin.com/in/ URL to https://www.linkedin.com/in/{slug}/"""
    m = re.search(r"linkedin\.com/in/([^/?#\s]+)", url)
    if m:
        return f"https://www.linkedin.com/in/{m.group(1)}/"
    return url


def _name_matches_url(name: str, url: str) -> bool:
    """
    Validate that a LinkedIn URL slug belongs to the searched person.
    Requires BOTH first and last name to appear as slug segments — prevents
    false matches where only one name token coincidentally appears.
    """
    # Strip honorifics / generational suffixes that never appear in slugs
    _SKIP = {"jr", "sr", "ii", "iii", "iv", "v", "dr", "mr", "ms", "mrs"}
    parts = [p for p in name.lower().split() if p not in _SKIP and len(p) >= 2]
    if len(parts) < 2:
        return False
    slug = re.search(r"linkedin\.com/in/([^/?#\s]+)", url)
    if not slug:
        return False
    slug_str = slug.group(1).lower()
    slug_parts = re.split(r"[-_0-9]", slug_str)

    first = parts[0]
    last = parts[-1]

    # Each name token must match the START of at least one slug segment
    first_ok = any(seg.startswith(first[:5]) for seg in slug_parts if len(seg) >= 3)
    last_ok = any(seg.startswith(last[:6]) for seg in slug_parts if len(seg) >= 3)

    return first_ok and last_ok


def enrich_with_apollo(name: str, company: str) -> dict:
    """
    Enrich a person using Apollo.io — returns email, phone, and verified LinkedIn URL.
    This is the PRIMARY contact enrichment tool. Call this for every person you find.
    Returns all three in one API call: email + direct phone + mobile + linkedin_url.
    """
    api_key = os.getenv("APOLLO_API_KEY", "")
    if not api_key:
        return {"found": False, "error": "APOLLO_API_KEY not set"}

    parts = name.strip().split()
    first_name = parts[0] if parts else ""
    last_name = parts[-1] if len(parts) > 1 else ""

    payload = {
        "api_key": api_key,
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": company,
    }

    data = _post(
        "https://api.apollo.io/v1/people/match",
        {"Content-Type": "application/json"},
        payload,
        timeout=20,
    )

    if "error" in data or not data.get("person"):
        # Fallback: try people search
        search_payload = {
            "api_key": api_key,
            "q_keywords": f"{name} {company}",
            "page": 1,
            "per_page": 1,
        }
        data2 = _post(
            "https://api.apollo.io/v1/mixed_people/search",
            {"Content-Type": "application/json"},
            search_payload,
            timeout=20,
        )
        people = data2.get("people", [])
        if people:
            person = people[0]
        else:
            return {"found": False, "name": name, "company": company,
                    "message": "No Apollo record found"}
    else:
        person = data["person"]

    # Extract phone numbers
    phones = person.get("phone_numbers", []) or []
    mobile = next((p["raw_number"] for p in phones if p.get("type") == "mobile"), "")
    direct = next((p["raw_number"] for p in phones if p.get("type") in ("direct", "work")), "")
    any_phone = mobile or direct or (phones[0]["raw_number"] if phones else "")

    linkedin_raw = person.get("linkedin_url", "") or ""
    linkedin_url = _normalize_linkedin_url(linkedin_raw) if linkedin_raw else ""

    return {
        "found": True,
        "name": person.get("name", name),
        "title": person.get("title", ""),
        "company": person.get("organization_name", company),
        "email": person.get("email", ""),
        "phone_mobile": mobile,
        "phone_direct": direct,
        "phone": any_phone,
        "linkedin_url": linkedin_url,
        "location": person.get("city", "") + (", " + person.get("state", "") if person.get("state") else ""),
        "source": "Apollo",
    }


def find_linkedin_url(name: str, company: str) -> dict:
    """
    Find the LinkedIn profile URL for a person using Exa.ai web search.
    FALLBACK — only use if enrich_with_apollo did not return a LinkedIn URL.
    Validates the URL actually belongs to the right person before returning it.
    """
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return {"found": False, "error": "EXA_API_KEY not set"}

    headers = {"x-api-key": api_key}

    for query in [
        f'"{name}" "{company}" site:linkedin.com/in',
        f'"{name}" {company} linkedin profile',
        f"{name} {company} linkedin",
    ]:
        payload = {
            "query": query,
            "numResults": 5,
            "useAutoprompt": False,
            "type": "neural",
            "includeDomains": ["linkedin.com"],
            "contents": {"text": {"maxCharacters": 400}},
        }
        data = _post("https://api.exa.ai/search", headers, payload)
        if data.get("error"):
            continue
        for r in data.get("results", []):
            raw_url = r.get("url", "")
            if "linkedin.com/in/" not in raw_url:
                continue
            # Validate: URL slug must contain part of the person's name
            if not _name_matches_url(name, raw_url):
                continue
            url = _normalize_linkedin_url(raw_url)
            text = r.get("text", "") or ""
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            headline = lines[0][:120] if lines else ""
            return {
                "found": True,
                "linkedin_url": url,
                "headline": headline,
                "name": name,
                "company": company,
            }

    return {"found": False, "linkedin_url": "", "name": name, "company": company}


def apify_linkedin_scrape(linkedin_urls: list[str]) -> dict:
    """
    Scrape full LinkedIn profiles using Apify actor 2SyF0bVxmgGr8IVCZ.
    Pass up to 15 LinkedIn profile URLs at once.
    Returns name, title, company, email, phone, location, about, experiences.
    This is the best way to get verified title, current company, and contact info.
    """
    token = os.getenv("APIFY_API_KEY", "")
    if not token:
        return {"profiles": [], "error": "APIFY_API_KEY not set"}

    if not linkedin_urls:
        return {"profiles": [], "error": "No LinkedIn URLs provided"}

    # Normalize all URLs to www.linkedin.com/in/ and deduplicate
    urls = list(dict.fromkeys(
        _normalize_linkedin_url(u) for u in linkedin_urls if "linkedin.com/in/" in u
    ))[:15]

    if not urls:
        return {"profiles": [], "error": "No valid linkedin.com/in/ URLs after normalization"}

    # 1. Start the actor run
    run_url = f"{APIFY_BASE}/acts/{APIFY_ACTOR_ID}/runs?token={token}"
    run_resp = _post(run_url, {}, {"profileUrls": urls}, timeout=30)

    if "error" in run_resp:
        return {"profiles": [], "error": f"Apify run start failed: {run_resp['error']}"}

    run_id = run_resp.get("data", {}).get("id", "")
    if not run_id:
        return {"profiles": [], "error": "Apify did not return a run ID"}

    # 2. Poll for completion (max 120 seconds)
    status_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={token}"
    for _ in range(40):
        time.sleep(3)
        status_data = _get(status_url)
        status = status_data.get("data", {}).get("status", "")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        return {"profiles": [], "error": f"Apify run ended with status: {status}"}

    # 3. Fetch dataset items
    dataset_id = run_resp.get("data", {}).get("defaultDatasetId", "")
    items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={token}&clean=true"
    items = _get(items_url)

    if isinstance(items, dict) and "error" in items:
        return {"profiles": [], "error": items["error"]}

    profiles = []
    for p in (items if isinstance(items, list) else []):
        profiles.append({
            "full_name": p.get("fullName", ""),
            "first_name": p.get("firstName", ""),
            "last_name": p.get("lastName", ""),
            "title": p.get("jobTitle", ""),
            "company": p.get("companyName", ""),
            "company_website": p.get("companyWebsite", ""),
            "company_linkedin": p.get("companyLinkedin", ""),
            "headline": p.get("headline", ""),
            "location": p.get("addressWithoutCountry", ""),
            "email": p.get("email") or "",
            "phone": p.get("mobileNumber") or "",
            "linkedin_url": p.get("linkedinPublicUrl", "") or p.get("linkedinUrl", ""),
            "about": (p.get("about") or "")[:400],
            "connections": p.get("connections", 0),
            "experiences": [
                {
                    "title": e.get("title", ""),
                    "company": e.get("companyName", ""),
                    "start": e.get("jobStartedOn", ""),
                    "end": e.get("jobEndedOn", ""),
                    "current": e.get("jobStillWorking", False),
                }
                for e in (p.get("experiences") or [])[:3]
            ],
        })

    return {
        "profiles": profiles,
        "count": len(profiles),
        "run_id": run_id,
        "source": "Apify/LinkedIn",
    }


def find_email(name: str, domain: str) -> dict:
    """
    Find a person's work email at a company domain using Hunter.io.
    Use when you know the company website domain (e.g. 'example.com').
    """
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key:
        return {"email": "", "error": "HUNTER_API_KEY not set"}

    parts = name.strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""

    if not (first and last and domain):
        return {"email": ""}

    params = urllib.parse.urlencode({
        "domain": domain, "first_name": first,
        "last_name": last, "api_key": api_key,
    })
    data = _get(f"https://api.hunter.io/v2/email-finder?{params}")
    if isinstance(data, dict):
        email = data.get("data", {}).get("email", "")
        score = data.get("data", {}).get("score", 0)
        # Only return if Hunter is reasonably confident this is the right person
        if email and score and int(score) >= 30:
            return {"email": email, "confidence": score, "source": "Hunter"}

    return {"email": ""}


# ── Tool definitions for Claude API ───────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "lookup_owner_company",
        "description": (
            "Look up property owner from NYC PLUTO dataset (free, no API key). "
            "Returns the company/entity name that owns the building. "
            "Always call this first for any NYC address."
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
            "Search the web using Exa.ai. Use to find: company official website, "
            "LinkedIn company page, leadership team mentions, executive names/titles, "
            "press releases, news articles about the company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results (1-8)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_webpage",
        "description": (
            "Fetch and read the text content of any webpage. "
            "Use on company websites to read their About, Team, Leadership, Management pages. "
            "Also returns links that look like leadership/team pages. "
            "Good for extracting executive names and titles directly from the company site."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "find_linkedin_url",
        "description": (
            "Find a person's LinkedIn profile URL using Exa search. "
            "Use after you have their name and company. "
            "Returns the linkedin.com/in/... URL needed for apify_linkedin_scrape."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's full name"},
                "company": {"type": "string", "description": "Company name"},
            },
            "required": ["name", "company"],
        },
    },
    {
        "name": "apify_linkedin_scrape",
        "description": (
            "Scrape full LinkedIn profiles from URLs using Apify. "
            "Pass up to 15 LinkedIn profile URLs at once. "
            "Returns: full name, job title, company, location, email, phone, about, experience history. "
            "Best source for verified current title and contact info. "
            "Call this ONCE with all URLs collected — do not call it one-by-one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "linkedin_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of LinkedIn profile URLs (linkedin.com/in/...)",
                },
            },
            "required": ["linkedin_urls"],
        },
    },
    {
        "name": "find_email",
        "description": (
            "Find a person's work email using Hunter.io. "
            "Use after you have their name and know the company's website domain. "
            "Call per-person after Apify scrape if email was not returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Person's full name"},
                "domain": {"type": "string", "description": "Company domain e.g. 'company.com'"},
            },
            "required": ["name", "domain"],
        },
    },
]


# ── Tool dispatcher ────────────────────────────────────────────────────────────

TOOL_MAP = {
    "enrich_with_apollo": enrich_with_apollo,
    "lookup_owner_company": lookup_owner_company,
    "search_web": search_web,
    "fetch_webpage": fetch_webpage,
    "find_linkedin_url": find_linkedin_url,
    "apify_linkedin_scrape": apify_linkedin_scrape,
    "find_email": find_email,
}


def call_tool(name: str, inputs: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**inputs)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": f"Tool {name} failed: {e}"})
