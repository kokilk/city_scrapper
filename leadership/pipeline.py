"""
Leadership Intelligence — Fast Pipeline

Given an address:
  1. Find the company that OWNS the building (PLUTO → DOB → web)
  1b. Resolve holding LLC to the real operating company
  2. Find that company's official website
  3. Extract the top 15 leaders from their team page
  4. Enrich each person: LinkedIn + email + phone (parallel)
  5. Batch Apify scrape for deep LinkedIn data
  6. Save CSV + JSON

Total time: ~15–40 seconds.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from leadership.tools import (
    search_web,
    fetch_webpage,
    find_linkedin_url,
    enrich_with_apollo,
    apollo_search_by_org,
    apify_linkedin_scrape,
    find_email,
    acris_current_owner,
    acris_owner_by_address,
    regrid_lookup,
    _normalize_linkedin_url,
    _get,
    _UA,
)
from leadership.validation import (
    validate_company,
    validate_people_batch,
    validate_emails_batch,
)
import urllib.parse

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "leadership"
MODEL = "claude-haiku-4-5-20251001"

# Domains that are brokers / aggregators / building-listing sites — never the owner's own website
_SKIP_DOMAINS = {
    # Brokers
    "cushmanwakefield", "cbre", "jll", "colliers", "newmark", "savills",
    "marcusmillichap", "berkadia", "eastdil", "ngkf",
    # Listing / aggregator sites
    "loopnet", "costar", "commercialcafe", "commercialsearch", "cityfeet",
    "crexi", "realgraph", "propertyshark", "streeteasy", "zillow", "trulia",
    "realtor", "apartments", "rent",
    # Data aggregators
    "rocketreach", "bloomberg", "crunchbase", "datanyze", "zoominfo", "dnb",
    "manta", "opencorporates", "bizjournals", "pitchbook", "owler",
    # News / reference
    "nytimes", "wsj", "bisnow", "globest", "therealdeal", "commercialobserver",
    "wikipedia", "linkedin", "yelp", "yellowpages",
    # Government / legal
    "sec.gov", "sunbiz", "dos.ny.gov",
    # Condo / residential building sites — these are the BUILDING's site, not the company's
    "condo", "lofts", "residences", "apartments", "rental",
}

# Words that indicate a URL is a specific building/property site, not a company site
_BUILDING_URL_WORDS = (
    "condo", "loft", "residenc", "apartment", "rental", "building",
    "plaza-north", "47th-ave", "jackson-ave", "queens-plaza",
)


def _claude(prompt: str, max_tokens: int = 512) -> str:
    """Single Claude Haiku call. Returns text."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    r = client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.content[0].text.strip()


def _is_skip_domain(url: str) -> bool:
    url_lower = url.lower()
    if any(s in url_lower for s in _SKIP_DOMAINS):
        return True
    if any(w in url_lower for w in _BUILDING_URL_WORDS):
        return True
    return False


# ── Step 1: Find raw building owner ──────────────────────────────────────────

def _pluto_lookup(address: str, city: str, zip_code: str = "") -> tuple[str, str, str, str]:
    """Try NYC PLUTO. Returns (owner_name, borough_code, block, lot)."""
    city_upper = city.upper().strip()
    borough_map = {
        "MANHATTAN": "MN", "NEW YORK": "MN", "BROOKLYN": "BK",
        "QUEENS": "QN", "BRONX": "BX", "STATEN ISLAND": "SI",
    }
    borough = borough_map.get(city_upper, "QN")

    addr_upper = address.strip().upper()
    m = re.match(r"^(\d[\d\-]*)\s+(.+)$", addr_upper)
    house = m.group(1) if m else ""
    street = m.group(2) if m else addr_upper

    # Build two search variants: full street name, and without suffix
    street_search = re.sub(
        r"\b(AVENUE|AVE|STREET|ST|ROAD|RD|BOULEVARD|BLVD|PLACE|PL|DRIVE|DR|LANE|LN|COURT|CT|NORTH|SOUTH|EAST|WEST)\b",
        "", street,
    ).strip()

    for search_term in [street, street_search]:
        if not search_term:
            continue
        zip_clause = f" AND zipcode = '{zip_code}'" if zip_code else ""
        # Include house number in query when available — avoids limit issues on busy streets
        house_clause = f" AND upper(address) like '{house} %'" if house else ""
        params = urllib.parse.urlencode({
            "$where": f"upper(address) like '%{search_term}%' AND borough = '{borough}'{zip_clause}{house_clause}",
            "$limit": "5",
        })
        raw = _get(f"https://data.cityofnewyork.us/resource/64uk-42ks.json?{params}")
        results = raw if isinstance(raw, list) else []

        if house and results:
            matched = [r for r in results if r.get("address", "").startswith(house)]
            if matched:
                r0 = matched[0]
                return r0.get("ownername", ""), borough, r0.get("block", ""), r0.get("lot", "")
            if len(results) == 1:
                r0 = results[0]
                return r0.get("ownername", ""), borough, r0.get("block", ""), r0.get("lot", "")
            results = []

        if results:
            r0 = results[0]
            return r0.get("ownername", ""), borough, r0.get("block", ""), r0.get("lot", "")

    return "", "", "", ""


def _dob_lookup(address: str, city: str) -> str:
    """Try NYC DOB permits for owner name."""
    city_upper = city.upper().strip()
    borough_map = {
        "MANHATTAN": "MANHATTAN", "NEW YORK": "MANHATTAN", "BROOKLYN": "BROOKLYN",
        "QUEENS": "QUEENS", "BRONX": "BRONX", "STATEN ISLAND": "STATEN ISLAND",
    }
    borough = borough_map.get(city_upper, "QUEENS")

    parts = address.strip().upper().split()
    house = parts[0] if parts and re.match(r"\d", parts[0]) else ""
    street_parts = parts[1:] if house else parts
    street = " ".join(street_parts)

    # Include house number in the WHERE clause directly for precise matching
    house_clause = f" AND house__ = '{house}'" if house else ""
    params = urllib.parse.urlencode({
        "$where": f"upper(street_name) like '%{street}%' AND upper(borough) = '{borough}'{house_clause}",
        "$limit": "5",
        "$order": "latest_action_date DESC",
    })
    raw = _get(f"https://data.cityofnewyork.us/resource/ic3t-wcy2.json?{params}")
    results = raw if isinstance(raw, list) else []

    # Collect all candidate owners and pick the best one
    candidates = []
    for r in results:
        biz = r.get("owner_s_business_name", "").strip()
        if biz:
            candidates.append(biz)

    # Prefer records with C/O (reveals actual operator) over generic holding LLCs
    for c in candidates:
        if " C/O " in c.upper():
            parts_co = re.split(r"\s+C/O\s+", c, flags=re.IGNORECASE)
            if len(parts_co) > 1 and len(parts_co[1].strip()) > 3:
                return parts_co[1].strip()

    # Return first non-empty candidate
    for c in candidates:
        return c

    # Fallback: personal name
    for r in results:
        name = " ".join(filter(None, [
            r.get("owner_s_first_name", ""),
            r.get("owner_s_last_name", ""),
        ])).strip()
        if name:
            return name

    return ""


def _web_owner_lookup(address: str, city: str, state: str) -> str:
    """Web search fallback for building owner. Reads snippets from ANY source (we're
    just extracting the name, not visiting these sites as the company website)."""
    queries = [
        f'"{address}" {city} {state} building owner developer company',
        f'"{address}" {city} owner developer real estate portfolio',
        f'{address} {city} {state} property owner who owns developer acquired',
    ]

    snippets = []
    for q in queries:
        r = search_web(q, 6)
        for item in r.get("results", []):
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").strip()[:250]
            # Include title — often contains company name even when snippet is nav-only text
            entry = f"TITLE: {title}\n{snippet}" if title else snippet
            snippets.append(entry)

    if not snippets:
        return ""

    combined = "\n".join(snippets[:8])
    prompt = (
        f"What company OWNS (not manages, not brokers, not leases) the building at "
        f"{address}, {city}, {state}?\n\n"
        f"Rules:\n"
        f"- Return ONLY the company name, nothing else\n"
        f"- Do NOT return brokers like Cushman & Wakefield, CBRE, JLL, Colliers, Newmark\n"
        f"- Do NOT return property managers, leasing agents, or condo associations\n"
        f"- Return the actual owner / developer / landlord / investment company\n"
        f"- If you cannot determine the owner, return exactly: UNKNOWN\n\n"
        f"Context:\n{combined}"
    )
    result = _claude(prompt, max_tokens=60)
    if "UNKNOWN" in result.upper() or len(result) > 120:
        return ""
    result = re.sub(
        r"^(The owner is|The company is|Based on|It appears|According to|The building is owned by)\s*",
        "", result, flags=re.IGNORECASE,
    )
    return result.strip().strip(".")


# ── Step 1b: Resolve holding LLC to operating company ────────────────────────

def _is_property_llc(name: str) -> bool:
    """Return True if the name looks like a property-specific or generic holding LLC."""
    n = name.upper()
    # Contains street reference (ordinal + avenue/street)
    if re.search(r"\b\d+(?:ST|ND|RD|TH)\b", n):
        return True
    if re.search(r"\b(AVENUE|AVE|STREET|ST|PLAZA|ROAD|RD)\b", n):
        return True
    # Starts with a number (like "1042 JACKSON LLC")
    if re.match(r"^\d+\s+", n):
        return True
    # Generic property-holding LLC patterns: "[Name] OWNER LLC", "[Name] PROPERTY LLC", etc.
    if re.search(r"\b(OWNER|HOLDING|HOLDINGS|PROPERTY|PROPERTIES|ACQUISITION|DEVELOPMENT|DEVELOPER)\b", n):
        return True
    return False


def _resolve_llc_to_company(llc_name: str, address: str, city: str, state: str) -> str:
    """
    Given a holding LLC name from PLUTO, find the actual operating company/developer.
    Returns the operating company name (or the cleaned LLC name if unresolvable).

    Examples:
      "JAMESTOWN 47TH AVENUE, LP."   → "Jamestown Properties"
      "1042 JACKSON LLC"              → "The Jackson Group"
      "BRAUSE PLAZA NORTH LLC"        → "Brause Realty"
      "5TH STREET LIC DEVELOPMENT"   → "5th Street Development" (keep as-is)
    """
    # Extract base company name by stripping LLC/LP and address-like content
    base = re.sub(
        r"\s*,?\s*\b(LLC|INC|CORP|LP|LTD|HOLDINGS?|TRUST|ASSOCIATES?|CO\.?)\b.*$",
        "", llc_name, flags=re.IGNORECASE,
    ).strip()
    # Remove ordinal street refs: "47TH AVENUE", "5TH STREET"
    base = re.sub(r"\b\d+(?:ST|ND|RD|TH)\s+(?:AVENUE|AVE|STREET|ST|ROAD|RD|BLVD|BOULEVARD|PLACE|PL)\b", "", base, flags=re.IGNORECASE)
    # Remove other address noise
    base = re.sub(r"\b(PLAZA|NORTH|SOUTH|EAST|WEST|LIC|TOWER|BUILDING)\b", "", base, flags=re.IGNORECASE)
    # Remove leading numbers (e.g. "1042 JACKSON" → "JACKSON")
    base = re.sub(r"^\d+\s+", "", base)
    base = re.sub(r"\s+", " ", base).strip().strip(",-")

    if len(base) < 3:
        base = llc_name  # couldn't simplify

    # Step 1: run the address-specific query first — most authoritative signal
    address_snippets = []
    r0 = search_web(f'"{address}" {state} owner acquired developer', 6)
    for item in r0.get("results", []):
        if not _is_skip_domain(item.get("url", "")):
            address_snippets.append(item.get("snippet", "")[:300])

    # If we got address-specific results, use ONLY those — avoids mixing with unrelated company data
    if address_snippets:
        snippets = address_snippets
    else:
        # Fallback: broader queries
        snippets = []
        for q in [
            f'"{base}" real estate {state} company developer investor',
            f'"{llc_name}" owner developer operator',
        ]:
            r = search_web(q, 5)
            for item in r.get("results", []):
                if not _is_skip_domain(item.get("url", "")):
                    snippets.append(item.get("snippet", "")[:300])

    if not snippets:
        return base

    combined = "\n".join(snippets[:6])
    prompt = (
        f"The building at {address}, {city}, {state} is owned by the LLC '{llc_name}'.\n"
        f"What is the actual operating company / developer / real estate firm behind this LLC?\n\n"
        f"Rules:\n"
        f"- Return ONLY the company name, nothing else\n"
        f"- Do NOT return brokers like Cushman & Wakefield, CBRE, JLL, Colliers\n"
        f"- Do NOT return condo associations, management firms, or leasing agents\n"
        f"- Return the developer, owner, or real estate investment firm that controls this entity\n"
        f"- If the LLC name itself IS the real company name, return it\n"
        f"- If you cannot determine, return: {base}\n\n"
        f"Context:\n{combined}"
    )
    result = _claude(prompt, max_tokens=80)
    result = re.sub(
        r"^(The operating company is|Based on|It appears|According to|The company is)\s*",
        "", result, flags=re.IGNORECASE,
    ).strip().strip(".")

    if not result or "UNKNOWN" in result.upper() or len(result) > 100:
        return base
    return result


def find_building_owner(address: str, city: str, state: str, zip_code: str = "") -> tuple[str, str, str]:
    """
    Find the company that owns a building.
    Returns (raw_entity_name, operating_company_name, source).

    Lookup order (most current → fallback):
      1. Regrid       — nationwide, most up-to-date deed data (when key set)
      2. NYC ACRIS    — real-time deed recordings (NYC only, via PLUTO block/lot)
      3. NYC PLUTO    — tax roll ownership (NYC only, may lag months)
      4. ACRIS direct — by street address when PLUTO has no record
      5. NYC DOB      — building permit applicant/owner
      6. Web search   — last resort
    """
    # 1. Regrid — try first regardless of city/state (nationwide, most current)
    regrid = regrid_lookup(address, city, state, zip_code)
    if regrid.get("owner"):
        raw = regrid["owner"]
        if _is_property_llc(raw):
            operating = _resolve_llc_to_company(raw, address, city, state)
        else:
            operating = raw
        return raw, operating, "Regrid"

    # 2. PLUTO — get block/lot, then check ACRIS for most recent deed
    pluto_raw, pluto_borough, block, lot = _pluto_lookup(address, city, zip_code)

    if pluto_raw:
        # Prefer ACRIS when available — it reflects actual recorded deed transfers
        acris_raw = acris_current_owner(pluto_borough, block, lot)
        raw = acris_raw if acris_raw else pluto_raw
        source = "NYC ACRIS" if acris_raw else "NYC PLUTO"

        if _is_property_llc(raw):
            operating = _resolve_llc_to_company(raw, address, city, state)
        else:
            operating = raw
        return raw, operating, source

    # 3. ACRIS by address — when PLUTO has no record, query ACRIS directly
    acris_raw = acris_owner_by_address(address, city)
    if acris_raw:
        if _is_property_llc(acris_raw):
            operating = _resolve_llc_to_company(acris_raw, address, city, state)
        else:
            operating = acris_raw
        return acris_raw, operating, "NYC ACRIS"

    # 4. DOB permits
    raw = _dob_lookup(address, city)
    if raw:
        operating = _resolve_llc_to_company(raw, address, city, state)
        looks_truncated = (
            operating.upper() == raw.upper()
            and len(operating) < 15
            and not re.search(r"\b(LLC|INC|CORP|GROUP|REALTY|CAPITAL|PARTNERS)\b", operating, re.I)
        )
        if looks_truncated:
            web = _web_owner_lookup(address, city, state)
            if web:
                operating = web
        return raw, operating, "NYC DOB"

    # 5. Web search fallback
    raw = _web_owner_lookup(address, city, state)
    return raw, raw, "Web Search"


# ── Step 2: Find company's official website ───────────────────────────────────

def find_company_website(company: str) -> str:
    """
    Find the official website for a company.
    Never returns aggregator/broker/building-specific/news sites.
    Validates domain starts with (or contains at word boundary) the company name.
    """
    # Full name minus only legal entity suffix — used for title exact-match (strong signal)
    company_title = re.sub(
        r"\s*,?\s*\b(LLC|INC|CORP|LP|LTD|LLP|CO\.?)\b.*$",
        "", company, flags=re.IGNORECASE,
    ).strip()

    # Cleaned name for domain/snippet word matching — strip generic words too
    company_clean = re.sub(
        r"\b(LLC|INC|CORP|LP|LTD|HOLDINGS?|REALTY|PROPERTIES|GROUP|PARTNERS?|CAPITAL|ASSOCIATES?)\b",
        "", company, flags=re.IGNORECASE,
    ).strip(" ,-")

    words = [w.lower() for w in re.split(r"[\s\-]+", company_clean) if len(w) >= 4]
    significant = [w for w in words if w not in ("real", "estate", "realty", "properties")]

    best_url = ""
    best_score = 0

    for query in [
        f'"{company_title}" NYC real estate official website',
        f'"{company}" NYC company website team leadership',
        f'{company_clean} New York real estate firm site',
    ]:
        results = search_web(query, 8)
        quoted_query = f'"{company_title}"' in query  # is full company name quoted?
        for pos, r in enumerate(results.get("results", [])):
            url = r.get("url", "")
            snippet = (r.get("snippet") or "").lower()
            title = (r.get("title") or "").lower()
            if _is_skip_domain(url):
                continue
            parsed = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if not parsed:
                continue
            domain = parsed.group(1).lower()
            domain_base = domain.split(".")[0]  # e.g. "nycsca" from "nycsca.org"

            # Domain word match: word or 4-char prefix appears at domain start or after hyphen
            all_words = words + [w[:4] for w in words if len(w) >= 5]
            domain_hits = sum(1 for w in all_words if re.search(r"(^|\-)" + re.escape(w), domain))
            # Acronym match: e.g. "sca" for "School Construction Authority" → nycsca.org
            stop = {"new", "york", "city", "the", "and", "for", "of"}
            acronym = "".join(w[0] for w in words if w not in stop)
            if len(acronym) >= 2:
                if domain_base == acronym:
                    domain_hits += 3  # exact: sca.gov
                elif domain_base.endswith(acronym):
                    domain_hits += 2  # embedded: nycsca.org
                elif acronym in domain_base:
                    domain_hits += 1  # partial
            # Title exact match: STRONGEST signal — full company name in the page title
            title_exact = 8 if company_title.lower() in title else 0
            # Title word hits: significant words in the page title
            title_hits = sum(1 for w in (significant or words) if w in title) * 2
            # Snippet word hits
            snippet_hits = sum(1 for w in (significant or words) if w in snippet)
            # Position bonus: first non-skip result for a quoted company name query is the
            # strongest possible signal that this is the official website
            position_bonus = 8 if (pos == 0 and quoted_query) else 0
            score = domain_hits * 2 + title_exact + title_hits + snippet_hits + position_bonus

            if score > best_score and domain_hits > 0:
                best_score = score
                best_url = url

    if best_url:
        # Normalize to root domain unless the subpath looks like a team/about page
        m_root = re.match(r"(https?://(?:www\.)?[^/]+)", best_url)
        path = best_url[len(m_root.group(1)):].lower() if m_root else ""
        team_kws = ("team", "leadership", "people", "about", "management", "executive", "bio", "profile", "principal")
        if m_root and not any(kw in path for kw in team_kws):
            return m_root.group(1)
        return best_url

    # Final fallback: first non-aggregator result
    results = search_web(f"{company_clean} real estate company website", 5)
    for r in results.get("results", []):
        url = r.get("url", "")
        if not _is_skip_domain(url):
            m_root = re.match(r"(https?://(?:www\.)?[^/]+)", url)
            return m_root.group(1) if m_root else url

    return ""


# ── Step 3: Scrape team page ──────────────────────────────────────────────────

def scrape_team_page(website_url: str) -> tuple[str, list[str]]:
    """
    Fetch the company website, find and scrape ALL team/leadership subpages found.
    Returns (combined_text, linkedin_profile_urls_found).
    """
    page = fetch_webpage(website_url)
    text = page.get("text", "")
    links = page.get("leadership_links", [])
    linkedin_profiles = list(page.get("linkedin_profiles_on_page", []))

    priority_kws = ("team", "leadership", "people", "management", "executives",
                    "about", "principals", "partners", "staff", "directors", "bios",
                    "governance", "board", "trustees", "officers")

    # Collect ALL candidate team pages (up to 3) ranked by keyword priority
    team_urls: list[str] = []
    for kw in priority_kws:
        for link in links:
            if kw in link.lower() and link != website_url and not _is_skip_domain(link):
                if link not in team_urls:
                    team_urls.append(link)
        if len(team_urls) >= 3:
            break

    # Also try common paths directly if not already found
    parsed = re.match(r"(https?://(?:www\.)?[^/]+)", website_url)
    if parsed:
        base = parsed.group(1)
        for path in ("/team", "/leadership", "/about/team", "/people", "/about", "/management",
                     "/governance", "/board", "/about-us", "/who-we-are"):
            candidate = base + path
            if candidate not in team_urls and candidate != website_url:
                team_urls.append(candidate)
                if len(team_urls) >= 5:
                    break

    # Fetch each candidate page (parallel)
    def _fetch_page(url: str) -> tuple[str, list[str]]:
        p = fetch_webpage(url)
        return p.get("text", ""), p.get("linkedin_profiles_on_page", [])

    subpage_text = ""
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [ex.submit(_fetch_page, u) for u in team_urls[:5]]
        for f in futures:
            t, li = f.result()
            if t:
                subpage_text += "\n" + t
            linkedin_profiles += li

    # Put team subpage content FIRST so it appears within the char window for extract_leaders
    combined = (subpage_text.strip() + "\n" + text).strip() if subpage_text.strip() else text
    return combined, list(dict.fromkeys(linkedin_profiles))


# ── Step 4: Extract people ────────────────────────────────────────────────────

def extract_leaders(page_text: str, company: str, max_chars: int = 4000) -> list[dict]:
    """
    ONE Claude call to extract leadership names + titles.
    Returns [{name, title}, ...] deduplicated, up to 15.
    """
    prompt = (
        f"Extract ALL leadership and senior staff of the company '{company}' from this text.\n\n"
        f"Return ONLY a valid JSON array (up to 15 entries). No explanation. No markdown fences.\n"
        f"Each object: {{\"name\": \"Full Name\", \"title\": \"Job Title\"}}\n\n"
        f"Include ALL of: CEO, President, Founder, COO, CFO, CTO, VP, Director, Partner, "
        f"Managing Director, Principal, Chairman, Head of, Board Member, Trustee, "
        f"Executive Director, Deputy Director, General Counsel, Senior Director, "
        f"Chief of Staff, Managing Partner, Senior Vice President.\n"
        f"Be thorough — extract every named executive, trustee, and senior leader you find.\n"
        f"Exclude: brokers, leasing agents, administrative staff, interns, "
        f"building superintendents, unnamed roles.\n"
        f"If no leadership people found, return []\n\n"
        f"TEXT:\n{page_text[:max_chars]}\n\nJSON:"
    )
    raw = _claude(prompt, max_tokens=1024)
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()

    try:
        people = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        try:
            people = json.loads(m.group(0)) if m else []
        except Exception:
            people = []

    seen: set[str] = set()
    unique = []
    for p in (people if isinstance(people, list) else []):
        if not p.get("name") or not p.get("title"):
            continue
        key = re.sub(r"[^a-z]", "", p["name"].lower())
        if key and key not in seen:
            seen.add(key)
            unique.append({"name": p["name"], "title": p["title"]})

    return unique[:15]


# ── Step 5: Parallel enrichment per person ────────────────────────────────────

def _web_search_email(name: str, company: str) -> str:
    """Scrape an email address from web search results as last-resort fallback."""
    results = search_web(f'"{name}" "{company}" email contact', 3)
    for r in results.get("results", []):
        found = re.findall(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            r.get("snippet", ""),
        )
        for email in found:
            # Skip generic/info/no-reply addresses
            if not re.match(r"^(info|contact|hello|team|support|admin|no.?reply)@", email, re.IGNORECASE):
                return email
    return ""


def _web_search_phone(name: str, company: str) -> str:
    """Try to find a direct phone number via web search."""
    results = search_web(f'"{name}" "{company}" phone direct', 3)
    for r in results.get("results", []):
        # US phone patterns: +1-212-555-0100, (212) 555-0100, 212.555.0100
        found = re.findall(
            r"(?:\+1[\s\-.]?)?\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}",
            r.get("snippet", ""),
        )
        if found:
            return found[0].strip()
    return ""


def _enrich_one(person: dict, company: str, domain: str) -> dict:
    """Find LinkedIn URL, email, and phone for one person.
    Apollo is the primary source (email + phone + verified LinkedIn in one call).
    Exa LinkedIn search and Hunter run in parallel as fallbacks.
    """
    prefetched: dict = person.pop("_apollo_prefetched", None) or {}

    if prefetched and prefetched.get("found"):
        apollo_r = prefetched
        with ThreadPoolExecutor(max_workers=2) as ex:
            li_f = ex.submit(find_linkedin_url, person["name"], company)
            em_f = ex.submit(find_email, person["name"], domain) if domain else None
            li_r = li_f.result()
            em_r = em_f.result() if em_f else {}
    else:
        with ThreadPoolExecutor(max_workers=3) as ex:
            apollo_f = ex.submit(enrich_with_apollo, person["name"], company)
            li_f = ex.submit(find_linkedin_url, person["name"], company)
            em_f = ex.submit(find_email, person["name"], domain) if domain else None
            apollo_r = apollo_f.result()
            li_r = li_f.result()
            em_r = em_f.result() if em_f else {}

    apollo_found = apollo_r.get("found", False)

    # LinkedIn: prefer Apollo (verified match) over Exa search result
    li_url = ""
    if apollo_found and apollo_r.get("linkedin_url"):
        li_url = apollo_r["linkedin_url"]
    elif li_r.get("found"):
        li_url = li_r.get("linkedin_url", "")

    # Email: prefer Apollo over Hunter
    email = ""
    email_source = ""
    if apollo_found and apollo_r.get("email"):
        email = apollo_r["email"]
        email_source = "Apollo"
    elif em_r.get("email"):
        email = em_r["email"]
        email_source = "Hunter"
    if not email:
        email = _web_search_email(person["name"], company)
        if email:
            email_source = "Web Search"

    # Phone: prefer Apollo over web search
    phone = ""
    if apollo_found and apollo_r.get("phone"):
        phone = apollo_r["phone"]
    if not phone:
        phone = _web_search_phone(person["name"], company)

    # LinkedIn source
    li_source = ""
    if li_url:
        li_source = "Apollo" if (apollo_found and apollo_r.get("linkedin_url")) else "Exa"

    contact_source = " | ".join(filter(None, [
        f"Email: {email_source}" if email_source else "",
        f"LinkedIn: {li_source}" if li_source else "",
    ])) or "Web Search"

    return {
        **person,
        "linkedin_url": li_url,
        "email": email,
        "phone": phone,
        "contact_source": contact_source,
    }


# ── Step 6–7: Apify + merge ───────────────────────────────────────────────────

def _apify_enrich(enriched: list[dict]) -> dict[str, dict]:
    """Batch Apify scrape. Returns {normalized_url: profile_dict}."""
    urls = list(dict.fromkeys(
        _normalize_linkedin_url(p["linkedin_url"])
        for p in enriched
        if p.get("linkedin_url") and "linkedin.com/in/" in p["linkedin_url"]
    ))
    if not urls:
        return {}

    result = apify_linkedin_scrape(urls)
    out: dict[str, dict] = {}
    for profile in result.get("profiles", []):
        url = _normalize_linkedin_url(profile.get("linkedin_url", ""))
        if url:
            out[url] = profile
    return out


# ── Main pipeline ──────────────────────────────────────────────────────────────
#
# Hard limits (never exceeded):
#   - Exa calls:    5  (3 general + 1 LinkedIn + 1 site or fallback)
#   - Claude calls: 2  (1 LLC resolve + 1 leader extraction)
#   - Hunter calls: 1 per person, no retry
#
# On any failure: print NOT FOUND and return [].

def run_pipeline(
    address: str,
    city: str,
    state: str,
    zip_code: str = "",
    verbose: bool = True,
    on_log=None,
) -> list[dict]:
    import shutil

    full_address = f"{address}, {city}, {state} {zip_code}".strip().rstrip(",")
    t0 = time.time()

    def log(msg: str) -> None:
        if verbose:
            print(f"  [{time.time()-t0:5.1f}s] {msg}")
        if on_log:
            on_log(msg)

    def not_found(reason: str) -> list[dict]:
        print(f"\n  NOT FOUND — {reason}")
        print(f"  Address: {full_address}\n")
        return []

    if verbose:
        print(f"\n{'='*62}")
        print(f"  LEADERSHIP PIPELINE")
        print(f"  {full_address}")
        print(f"{'='*62}")

    # ── Step 1: Owner lookup (PLUTO → DOB → Exa) — one attempt each ──────────
    log("Step 1/4 — Building owner (NYC open data)...")
    raw_entity, company, owner_source = find_building_owner(address, city, state, zip_code)

    if not raw_entity:
        return not_found("building owner not found in PLUTO / DOB / Exa")

    if not company:
        company = raw_entity

    if raw_entity == company:
        log(f"  Owner: {raw_entity}")
    else:
        log(f"  Registered entity: {raw_entity}")
        log(f"  Operating company: {company}")

    # ── Checkpoint 1: Validate company from 2 independent sources ────────────
    log(f"  Validating company: {company}...")
    company_validation = validate_company(company, address, city, state)
    log(f"  Company confidence: {company_validation['confidence']} ({company_validation['sources_found']}/2 sources) — {company_validation['validation_note']}")

    # Strip legal suffixes for search queries
    company_search = re.sub(
        r"\s*\b(LLC|INC|CORP|LP|LTD|HOLDINGS?|REALTY|GROUP|PARTNERS?|CAPITAL|ASSOCIATES?|TRUST)\b.*$",
        "", company, flags=re.IGNORECASE,
    ).strip(" ,-") or company

    # ── Step 2: Find website — one Exa call ───────────────────────────────────
    log(f"Step 2/4 — Company website (Exa): {company}...")
    website = find_company_website(company)
    if not website and company_search != company:
        website = find_company_website(company_search)

    # Sanity check — reject websites whose domain has zero overlap with company name
    if website:
        domain_m = re.search(r"https?://(?:www\.)?([^/]+)", website)
        domain_check = domain_m.group(1).lower().replace("-", "").replace(".", "") if domain_m else ""
        # Only check distinctive words — strip generic real estate terms
        _generic = {"real", "estate", "realty", "properties", "property", "group",
                    "capital", "partners", "healthcare", "medical", "services",
                    "management", "investment", "investments", "holdings", "ventures"}
        company_words = [
            w.lower() for w in re.split(r"[\s\-]+", company_search)
            if len(w) >= 4 and w.lower() not in _generic
        ]
        domain_matches = bool(company_words) and any(w[:5] in domain_check for w in company_words)
        if not domain_matches:
            website = ""  # domain is unrelated — discard it

    domain_m = re.search(r"https?://(?:www\.)?([^/]+)", website) if website else None
    domain = domain_m.group(1) if domain_m else ""
    log(f"  Website: {website or 'not found — using web search only'}")

    # ── Step 3: Gather all text + Apollo org search in parallel ──────────────
    log("Step 3/4 — Gathering leadership data...")

    apollo_people_future = None
    with ThreadPoolExecutor(max_workers=2) as gather_ex:
        # 3a. Scrape website
        page_text = ""
        linkedin_from_page: list[str] = []

        # 3b. Apollo org search — runs in background while we scrape + search Exa
        apollo_people_future = gather_ex.submit(apollo_search_by_org, company, 15)

        if website:
            page_text, linkedin_from_page = scrape_team_page(website)
            log(f"  Website: {len(page_text)} chars scraped")

    # Detect JS-rendered garbage (navigation menus instead of content)
    js_garbage = (
        page_text.count("Loading") > 3
        or page_text.count("Translate") > 3
        or page_text.count("CONTRAST") > 3
    )

    # Collect Apollo org results
    apollo_org_people: list[dict] = []
    if apollo_people_future:
        try:
            apollo_org_people = apollo_people_future.result() or []
        except Exception:
            apollo_org_people = []
    if apollo_org_people:
        log(f"  Apollo: {len(apollo_org_people)} people found at {company}")

    # 3c. Exa search — exactly 5 queries, no retry
    exa_queries = [
        f'"{company}" CEO president founder chairman leadership executives',
        f'"{company}" managing director vice president CFO COO principal officer',
        f'"{company_search}" board trustees directors leadership team',
        f'site:linkedin.com "{company_search}" director vice president New York',
    ]
    if domain:
        exa_queries.append(f'site:{domain} leadership team executives board management')
    else:
        exa_queries.append(f'"{company_search}" senior director executive biography profile')

    seen_urls: set[str] = set()
    all_snippets: list[str] = []
    for q in exa_queries:
        for r in search_web(q, 8, text_chars=800).get("results", []):
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                entry = (f"{title}: {snippet}" if title else snippet)[:700]
                all_snippets.append(entry)

    snippets_text = "\n---\n".join(all_snippets)

    # Snippets first when site is JS-rendered (page_text is nav noise)
    if js_garbage or not page_text:
        combined_text = (snippets_text + "\n" + page_text).strip()
    else:
        combined_text = (page_text + "\n" + snippets_text).strip()

    # ── Step 4: ONE Claude extraction call ────────────────────────────────────
    log("Step 4/4 — Extracting leaders + enriching contacts...")
    people = extract_leaders(combined_text, company, max_chars=16000)

    # Build a lookup of Apollo org results by name for enrichment shortcut
    apollo_org_by_name: dict[str, dict] = {}
    for ap in apollo_org_people:
        ap_name = ap.get("name", "").strip()
        if ap_name:
            apollo_org_by_name[ap_name.lower()] = ap

    # Merge Apollo org people: add anyone not already in Claude's list
    if apollo_org_people:
        existing_names = {p["name"].lower() for p in people}
        for ap in apollo_org_people:
            ap_name = ap.get("name", "").strip()
            if ap_name and ap_name.lower() not in existing_names:
                people.append({
                    "name": ap_name,
                    "title": ap.get("title", ""),
                    "_apollo_prefetched": ap,
                })
                existing_names.add(ap_name.lower())

    if not people:
        log(f"  No leaders found for '{company}' — returning company info only")
        placeholder = [{
            "rank": 1,
            "full_name": "",
            "title": "",
            "company": company,
            "email": "",
            "phone": "",
            "linkedin_url": "",
            "confidence": "Low",
            "property_address": full_address,
            "owner_entity": raw_entity,
            "data_source": f"Owner: {owner_source} | Contacts: —",
            "person_verified": False,
            "person_sources": 0,
            "person_validation_note": "No leadership data publicly available",
            "email_valid": False,
            "email_deliverable": None,
            "email_check_note": "—",
            "company_confidence": company_validation["confidence"],
            "company_validation_note": company_validation["validation_note"],
        }]
        return placeholder

    log(f"  {len(people)} people: {', '.join(p['name'] for p in people[:4])}{'...' if len(people) > 4 else ''}")

    # ── Step 5: Parallel enrichment — one Hunter + one Exa call per person ────
    enriched: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_enrich_one, p, company, domain): p for p in people}
        for future in as_completed(futures):
            r = future.result()
            if not r.get("linkedin_url"):
                for li_url in linkedin_from_page:
                    slug_m = re.search(r"linkedin\.com/in/([^/?#]+)", li_url)
                    if slug_m:
                        name_key = r["name"].lower().replace(" ", "")
                        if name_key[:5] in slug_m.group(1).lower():
                            r["linkedin_url"] = _normalize_linkedin_url(li_url)
                            break
            enriched.append(r)
            li_m = "✓ LinkedIn" if r.get("linkedin_url") else "—"
            em_m = r.get("email") or "—"
            log(f"  {r['name']} | {em_m} | {li_m}")

    # ── Checkpoint 2: Validate people (first 15, parallel) ───────────────────
    log("  Validating people...")
    enriched = validate_people_batch(enriched, company)

    # ── Checkpoint 3: Validate emails (parallel) ──────────────────────────────
    log("  Validating emails...")
    enriched = validate_emails_batch(enriched)

    # ── Build final result list ────────────────────────────────────────────────
    leaders: list[dict] = []
    for i, p in enumerate(enriched, 1):
        li_url = _normalize_linkedin_url(p.get("linkedin_url", ""))
        email = p.get("email") or ""
        phone = p.get("phone") or ""
        has_li = bool(li_url)
        has_em = bool(email)
        email_ok = p.get("email_valid", False)

        # Confidence now factors in validation
        person_verified = p.get("verified", False)
        if has_li and has_em and email_ok and person_verified:
            conf = "High"
        elif (has_li or has_em) and person_verified:
            conf = "Medium"
        elif has_li or has_em:
            conf = "Low"
        else:
            conf = "Unverified"

        contact_source = p.get("contact_source", "—")
        data_source = f"Owner: {owner_source} | Contacts: {contact_source}"

        leaders.append({
            "rank": i,
            "full_name": p["name"],
            "title": p["title"],
            "company": company,
            "email": email,
            "phone": phone,
            "linkedin_url": li_url,
            "confidence": conf,
            "property_address": full_address,
            "owner_entity": raw_entity,
            "data_source": data_source,
            # Validation fields
            "person_verified":        p.get("verified", False),
            "person_sources":         p.get("person_sources", 0),
            "person_validation_note": p.get("person_validation_note", "—"),
            "email_valid":            p.get("email_valid", False),
            "email_deliverable":      p.get("email_deliverable"),
            "email_check_note":       p.get("email_check_note", "—"),
            "company_confidence":     company_validation["confidence"],
            "company_validation_note": company_validation["validation_note"],
        })

    # ── Save + clean up old files for this address ────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    addr_slug = re.sub(r"[^A-Za-z0-9]", "_", full_address)[:40]

    fields = ["rank", "full_name", "title", "company", "email", "phone",
              "linkedin_url", "confidence", "property_address", "owner_entity", "data_source",
              "person_verified", "person_sources", "person_validation_note",
              "email_valid", "email_check_note", "company_confidence", "company_validation_note"]

    csv_path = OUTPUT_DIR / f"{addr_slug}_{timestamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in leaders)

    json_path = csv_path.with_suffix(".json")
    json_path.write_text(json.dumps(leaders, indent=2))

    # Delete older files for the same address slug
    for old in OUTPUT_DIR.glob(f"{addr_slug}_*.csv"):
        if old != csv_path:
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)

    shutil.copy2(csv_path, OUTPUT_DIR / "leadership_latest.csv")
    (OUTPUT_DIR / "leadership_latest.json").write_text(json.dumps(leaders, indent=2))

    if verbose:
        total = time.time() - t0
        print(f"\n{'='*62}")
        print(f"  RESULTS — {len(leaders)} leaders | {company} | {total:.0f}s\n")
        for ldr in leaders:
            conf_label = f"[{ldr['confidence']:<6}]"
            em = ldr["email"] or "—"
            ph = ldr["phone"] or "—"
            li = "✓ LinkedIn" if ldr["linkedin_url"] else "—"
            print(f"  [{ldr['rank']:>2}] {conf_label} {ldr['title']}")
            print(f"        {ldr['full_name']} | {em} | {ph} | {li}")
        print(f"\n  CSV  → {csv_path}")
        print(f"  JSON → {json_path}")
        print(f"{'='*62}\n")

    return leaders

def parse_full_address(raw: str) -> tuple[str, str, str, str]:
    """
    Parse a full address string into (street, city, state, zip).
    Handles formats like:
      "30-30 47th Avenue, Long Island City, Queens, NY 11101"
      "30-30 47th Avenue, Queens, NY 11101"
      "350 5th Ave, New York, NY 10118"
    """
    raw = raw.strip().rstrip(",")

    # Extract ZIP (5-digit at end)
    zip_code = ""
    m = re.search(r"\b(\d{5})\s*$", raw)
    if m:
        zip_code = m.group(1)
        raw = raw[:m.start()].rstrip(", ")

    # Extract state (2-letter at end after ZIP removal)
    state = "NY"
    m = re.search(r",?\s*\b([A-Z]{2})\s*$", raw)
    if m:
        state = m.group(1)
        raw = raw[:m.start()].rstrip(", ")

    # Split remaining into parts
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if len(parts) == 1:
        return parts[0], "", state, zip_code

    street = parts[0]

    # City/borough: last meaningful part
    # Queens addresses often have "Long Island City, Queens" — take the last part as borough
    borough_names = {"queens", "brooklyn", "manhattan", "bronx", "staten island",
                     "new york", "long island city", "astoria", "flushing"}
    city = parts[-1]
    for part in reversed(parts[1:]):
        if part.lower() in borough_names:
            city = part
            break

    return street, city, state, zip_code


def run_addresses(addresses: list[str], append: bool = False) -> None:
    """Run the pipeline for a list of full address strings and write combined latest.

    append=True: load existing leadership_latest.csv first and add new results to it.
    """
    import shutil
    import time as _time

    t_start = _time.time()

    fields = ["rank", "full_name", "title", "company", "email", "phone",
              "linkedin_url", "confidence", "property_address", "owner_entity", "data_source"]

    # Load existing results if appending
    existing_leaders: list[dict] = []
    latest_csv = OUTPUT_DIR / "leadership_latest.csv"
    if append and latest_csv.exists():
        with latest_csv.open(newline="", encoding="utf-8") as f:
            existing_leaders = list(csv.DictReader(f))
        print(f"  Loaded {len(existing_leaders)} existing leaders from leadership_latest.csv")

    new_leaders: list[dict] = []
    for raw in addresses:
        raw = raw.strip()
        if not raw:
            continue
        street, city, state, zip_code = parse_full_address(raw)
        if not city:
            city = "Queens"
        result = run_pipeline(street, city, state, zip_code)
        new_leaders.extend(result)

    all_leaders = existing_leaders + new_leaders

    if all_leaders:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with latest_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows({k: r.get(k, "") for k in fields} for r in all_leaders)
        (OUTPUT_DIR / "leadership_latest.json").write_text(json.dumps(all_leaders, indent=2))

        elapsed = _time.time() - t_start
        print(f"\n{'='*62}")
        print(f"  DONE in {elapsed:.0f}s")
        print(f"  New leaders this run : {len(new_leaders)}")
        print(f"  Total in file        : {len(all_leaders)}")
        print(f"  → {latest_csv}")
        print(f"{'='*62}\n")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="Leadership intelligence pipeline",
        epilog="Examples:\n"
               "  python3 leadership_fast.py '30-30 47th Avenue, Queens, NY 11101'\n"
               "  python3 leadership_fast.py --address '30-30 47th Ave' --city Queens --state NY --zip 11101",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Mode 1: full address string(s) as positional args
    p.add_argument("full_addresses", nargs="*", help="Full address(es) e.g. '30-30 47th Ave, Queens, NY 11101'")
    # Mode 2: legacy separate flags
    p.add_argument("--address")
    p.add_argument("--city")
    p.add_argument("--state", default="NY")
    p.add_argument("--zip", default="", dest="zip_code")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--append", action="store_true",
                   help="Add results to existing leadership_latest.csv instead of overwriting")
    args = p.parse_args()

    if args.full_addresses:
        run_addresses(args.full_addresses, append=args.append)
    elif args.address and args.city:
        run_pipeline(args.address, args.city, args.state, args.zip_code, not args.quiet)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
