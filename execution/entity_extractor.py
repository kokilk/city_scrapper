"""
Stage 2: Entity Extraction and Role Assignment

Reads all Stage 1 output files and produces a unified list of
StakeholderCandidate objects, each with a role classification.

Role inference logic (in priority order):
  - PLUTO / Assessor owner_name   → Owner
  - Permit applicant_title = ARCHITECT → Architect
  - Permit applicant_title = ENGINEER  → Architect (structural/MEP)
  - Permit contractor_name         → GC
  - Permit applicant ≠ owner       → Developer (probable)
  - OpenCorporates officer          → Developer / Owner

Sources used (all free):
  - permits.json        from permit_scraper.py  (NYC DOB or generic)
  - pluto_owner.json    from pluto_lookup.py    (NYC PLUTO)
  - county_assessor.json from county_assessor_fetch.py (other cities)
  - opencorporates_entities.json from opencorporates_entity_lookup.py

Output: .tmp/stakeholder_candidates.json  (list of StakeholderCandidate dicts)
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from models import StakeholderCandidate, SourceReference

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE = Path(__file__).parent.parent / ".tmp"
PERMITS_PATH = BASE / "permits.json"           # from permit_scraper.py
PLUTO_PATH = BASE / "pluto_owner.json"         # from pluto_lookup.py
ASSESSOR_PATH = BASE / "county_assessor.json"  # from county_assessor_fetch.py
ENTITIES_PATH = BASE / "opencorporates_entities.json"
ADDR_PATH = BASE / "normalized_address.json"
OUTPUT_PATH = BASE / "stakeholder_candidates.json"

# ── Classification patterns ────────────────────────────────────────────────────

ARCHITECT_RE = re.compile(r"\b(architect|architecture|design|designer|planning)\b", re.IGNORECASE)
GC_RE = re.compile(r"\b(general|contractor of record|builder|construction mgmt)\b", re.IGNORECASE)
SPECIALTY_RE = re.compile(
    r"\b(electrical|plumbing|hvac|mechanical|roofing|framing|concrete|masonry|"
    r"glazing|curtain wall|drywall|insulation|flooring|tile|painting|landscaping|"
    r"elevator|fire|sprinkler|structural|steel|demolition|grading|excavation|"
    r"waterproofing|foundation|solar|pv|signage|low voltage|telecom)\b",
    re.IGNORECASE,
)
ENTITY_RE = re.compile(
    r"\b(LLC|L\.L\.C|LP|L\.P|LLP|Inc\.?|Corp\.?|Trust|REIT|"
    r"Holdings|Partners|Realty|Properties|Group|Foundation)\b",
    re.IGNORECASE,
)


def _classify_contractor(classification: str) -> str:
    if ARCHITECT_RE.search(classification):
        return "Architect"
    if GC_RE.search(classification):
        return "GC"
    if SPECIALTY_RE.search(classification):
        return "Subcontractor"
    return "GC"   # default: treat unknown contractors as GC


def _parse_date_str(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


def _names_match(a: str, b: str) -> bool:
    """Loose name equality: normalize case and strip legal suffixes."""
    def clean(s: str) -> str:
        s = ENTITY_RE.sub("", s).lower()
        return re.sub(r"[^a-z0-9 ]", "", s).strip()
    return clean(a) == clean(b) and bool(clean(a))


def _make_ref(source: str, record_id: str, record_date_str: str | None, url: str = "") -> dict[str, Any]:
    return {
        "source_name": source,
        "record_id": record_id,
        "record_date": record_date_str or str(date.today()),
        "raw_url": url,
    }


def _classify_applicant_title(title: str) -> str:
    """Map NYC DOB applicant professional title to our role."""
    t = title.upper()
    if "ARCHITECT" in t:
        return "Architect"
    if "ENGINEER" in t:
        return "Architect"   # structural/MEP engineers listed here
    if "EXPEDITOR" in t or "FILING REP" in t:
        return "Unknown"
    return "Developer"


def extract(
    permits: list[dict[str, Any]],
    pluto: dict[str, Any],
    assessor: dict[str, Any],
    entities: dict[str, Any],
    property_address: str,
    county_fips: str,
) -> list[dict[str, Any]]:

    candidates: list[StakeholderCandidate] = []

    # ── 1. PLUTO / County Assessor: Property Owner ───────────────────────────
    pluto_owner = pluto.get("owner_name", "")
    assessor_owner = assessor.get("owner_name", "")
    primary_owner = pluto_owner or assessor_owner
    source_label = "NYC_PLUTO" if pluto_owner else "CountyAssessor"

    owner_ref = _make_ref(
        source_label,
        pluto.get("block", "") or assessor.get("parcel_id", ""),
        str(date.today()),
    )
    if primary_owner:
        candidates.append(StakeholderCandidate(
            raw_name=primary_owner,
            role="Owner",
            company=primary_owner if ENTITY_RE.search(primary_owner) else "",
            source_records=[SourceReference(**owner_ref)],
        ))

    # Cross-ref: if assessor has different owner from PLUTO, add separately
    if assessor_owner and pluto_owner and not _names_match(assessor_owner, pluto_owner):
        assessor_ref = _make_ref("CountyAssessor", assessor.get("parcel_id", ""), str(date.today()))
        candidates.append(StakeholderCandidate(
            raw_name=assessor_owner,
            role="Owner",
            company=assessor_owner if ENTITY_RE.search(assessor_owner) else "",
            source_records=[SourceReference(**assessor_ref)],
        ))

    # ── 2. Permit data: Applicant, Architect, GC, Owner from permits ─────────
    seen_names: set[str] = set()

    for permit in permits:
        source = permit.get("source", "NYC_DOB")
        permit_ref = _make_ref(
            source,
            permit.get("permit_id", ""),
            permit.get("file_date"),
        )

        # Permit applicant — classify by professional title
        applicant = permit.get("applicant_name", "").strip()
        title = permit.get("applicant_title", "")
        if applicant and applicant not in seen_names:
            seen_names.add(applicant)
            role = _classify_applicant_title(title)
            # If applicant matches owner → skip (already captured above)
            if not _names_match(applicant, primary_owner):
                candidates.append(StakeholderCandidate(
                    raw_name=applicant,
                    role=role,  # type: ignore[arg-type]
                    company=applicant if ENTITY_RE.search(applicant) else "",
                    source_records=[SourceReference(**permit_ref)],
                    flags=["SINGLE_SOURCE"],
                ))

        # Permit owner (if different from PLUTO/assessor owner)
        p_owner = permit.get("owner_name", "").strip()
        if p_owner and p_owner not in seen_names and not _names_match(p_owner, primary_owner):
            seen_names.add(p_owner)
            candidates.append(StakeholderCandidate(
                raw_name=p_owner,
                role="Owner",
                company=p_owner if ENTITY_RE.search(p_owner) else "",
                source_records=[SourceReference(**permit_ref)],
            ))

        # Contractor of record → GC
        contractor = permit.get("contractor_name", "").strip()
        if contractor and contractor not in seen_names:
            seen_names.add(contractor)
            candidates.append(StakeholderCandidate(
                raw_name=contractor,
                role="GC",
                company=contractor,
                source_records=[SourceReference(**permit_ref)],
                flags=["SINGLE_SOURCE"],
            ))

    # ── 3. OpenCorporates: Officers of LLC entities ───────────────────────────
    for entity_name, company_data in entities.items():
        officers = company_data.get("officers", [])
        oc_ref = _make_ref(
            "OpenCorporates",
            company_data.get("company_number", ""),
            str(date.today()),
            company_data.get("source", {}).get("raw_url", ""),
        )
        for officer in officers:
            if officer.get("end_date"):
                continue  # skip former officers
            position = officer.get("position", "").lower()
            if "manager" in position or "member" in position or "president" in position or "ceo" in position:
                role = "Developer"
            elif "agent" in position or "register" in position:
                role = "Unknown"
            else:
                role = "Owner"

            candidates.append(StakeholderCandidate(
                raw_name=officer.get("name", ""),
                role=role,  # type: ignore[arg-type]
                company=entity_name,
                source_records=[SourceReference(**oc_ref)],
            ))

    # Filter blanks and unknowns
    candidates = [c for c in candidates if c.raw_name.strip() and c.role != "Unknown"]

    return [asdict(c) for c in candidates]


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _load(path: Path, default: Any) -> Any:
        return json.loads(path.read_text()) if path.exists() else default

    permits = _load(PERMITS_PATH, [])
    pluto = _load(PLUTO_PATH, {})
    assessor = _load(ASSESSOR_PATH, {})
    entities = _load(ENTITIES_PATH, {})
    addr = _load(ADDR_PATH, {})

    property_address = (
        f"{addr.get('delivery_line_1', '')}, "
        f"{addr.get('city', '')}, "
        f"{addr.get('state', '')} {addr.get('zip5', '')}"
    ).strip(", ")
    county_fips = addr.get("county_fips", "")

    candidates = extract(permits, pluto, assessor, entities, property_address, county_fips)

    OUTPUT_PATH.write_text(json.dumps(candidates, indent=2, default=str))
    print(f"[entity_extractor] Extracted {len(candidates)} stakeholder candidate(s) → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
