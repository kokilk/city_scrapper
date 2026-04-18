"""
Stage 6: Deduplication

Merges stakeholders that refer to the same person or entity, using this
priority order:
  1. Phone number exact match (E.164-normalized)
  2. Email exact match (lowercased)
  3. LinkedIn URL exact match
  4. Name fuzzy match (rapidfuzz token_sort_ratio > 88) + same company

When merging:
  - Union all source_records
  - Keep the highest confidence_score
  - Keep the name/company from the highest-authority source
  - Union all flags
  - Assign a UUID stakeholder_id

Do NOT merge: same name + different non-empty companies → keep separate.

Input:  .tmp/scored_stakeholders.json
Output: .tmp/final_stakeholders.json
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("[deduplicator] WARNING: rapidfuzz not installed — name fuzzy matching disabled", file=sys.stderr)

sys.path.insert(0, str(Path(__file__).parent))
from confidence_scorer import SOURCE_WEIGHTS

INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "scored_stakeholders.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "final_stakeholders.json"

FUZZY_THRESHOLD = 88
ENTITY_SUFFIX_RE = re.compile(
    r"\b(LLC|L\.L\.C\.?|LP|L\.P\.?|LLP|L\.L\.P\.?|Inc\.?|Corp\.?|"
    r"Trust|REIT|Holdings|Partners|Realty|Properties|Group|Foundation)\b",
    re.IGNORECASE,
)
PHONE_CLEAN_RE = re.compile(r"[^\d+]")


def _normalize_phone(phone: str) -> str:
    """Strip non-digit chars except leading +, normalize to 10 digits."""
    cleaned = PHONE_CLEAN_RE.sub("", phone)
    if cleaned.startswith("+1") and len(cleaned) == 12:
        return cleaned
    if len(cleaned) == 11 and cleaned.startswith("1"):
        return f"+{cleaned}"
    if len(cleaned) == 10:
        return f"+1{cleaned}"
    return cleaned


def _normalize_name(name: str) -> str:
    """Lowercase, strip entity suffixes, remove punctuation."""
    s = ENTITY_SUFFIX_RE.sub("", name).lower()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def _source_authority(source_records: list[dict[str, Any]]) -> float:
    """Sum of source weights for ranking which record wins on merge."""
    return sum(
        SOURCE_WEIGHTS.get(r.get("source_name", ""), 0.05)
        for r in source_records
    )


def _merge(winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, Any]:
    """Merge loser into winner. Winner keeps name/company; both contribute sources."""
    merged = dict(winner)

    # Union source records (deduplicate by record_id)
    existing_ids = {r.get("record_id") for r in merged.get("source_records", [])}
    for ref in loser.get("source_records", []):
        if ref.get("record_id") not in existing_ids:
            merged.setdefault("source_records", []).append(ref)
            existing_ids.add(ref.get("record_id"))

    # Keep highest confidence score
    merged["confidence_score"] = max(
        merged.get("confidence_score", 0),
        loser.get("confidence_score", 0),
    )
    merged["confidence_label"] = _label(merged["confidence_score"])

    # Union flags
    all_flags = set(merged.get("flags", [])) | set(loser.get("flags", []))
    merged["flags"] = sorted(all_flags)

    # Union enrichment sources
    enrich = set(merged.get("enrichment_sources", [])) | set(loser.get("enrichment_sources", []))
    merged["enrichment_sources"] = sorted(enrich)

    # Fill contact gaps from loser if winner is missing them
    for field in ("email", "phone", "linkedin_url"):
        if not merged.get(field) and loser.get(field):
            merged[field] = loser[field]

    # Recompute independent_source_count
    groups: set[str] = set()
    from models import INDEPENDENT_SOURCE_GROUPS
    for ref in merged.get("source_records", []):
        sn = ref.get("source_name", "")
        groups.add(INDEPENDENT_SOURCE_GROUPS.get(sn, sn))
    merged["independent_source_count"] = len(groups)

    return merged


def _label(score: float) -> str:
    if score >= 75:
        return "Verified"
    if score >= 45:
        return "Probable"
    return "Unconfirmed"


def deduplicate(stakeholders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Union-Find approach: build clusters then merge each cluster
    n = len(stakeholders)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    # Build lookup tables for O(1) match checks
    phones: dict[str, int] = {}
    emails: dict[str, int] = {}
    linkedins: dict[str, int] = {}

    for i, s in enumerate(stakeholders):
        phone = _normalize_phone(s.get("phone", ""))
        if phone and len(phone) >= 10:
            if phone in phones:
                union(i, phones[phone])
            else:
                phones[phone] = i

        email = (s.get("email", "") or "").lower().strip()
        if email:
            if email in emails:
                union(i, emails[email])
            else:
                emails[email] = i

        linkedin = (s.get("linkedin_url", "") or "").strip().rstrip("/")
        if linkedin:
            if linkedin in linkedins:
                union(i, linkedins[linkedin])
            else:
                linkedins[linkedin] = i

    # Fuzzy name matching (O(n²) but n is typically small per property)
    if HAS_RAPIDFUZZ:
        names = [_normalize_name(s.get("raw_name", "")) for s in stakeholders]
        companies = [(s.get("company", "") or "").lower().strip() for s in stakeholders]

        for i in range(n):
            if not names[i]:
                continue
            for j in range(i + 1, n):
                if not names[j]:
                    continue
                if find(i) == find(j):
                    continue  # already merged

                # Do NOT merge if both have non-empty, different companies
                ci, cj = companies[i], companies[j]
                if ci and cj and ci != cj:
                    continue

                ratio = fuzz.token_sort_ratio(names[i], names[j])
                if ratio >= FUZZY_THRESHOLD:
                    union(i, j)

    # Build clusters
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    # Merge each cluster
    results = []
    for root, members in clusters.items():
        if len(members) == 1:
            merged = dict(stakeholders[members[0]])
        else:
            # Sort by source authority descending — winner is most authoritative
            sorted_members = sorted(
                members,
                key=lambda i: _source_authority(stakeholders[i].get("source_records", [])),
                reverse=True,
            )
            merged = dict(stakeholders[sorted_members[0]])
            for idx in sorted_members[1:]:
                merged = _merge(merged, stakeholders[idx])

        # Assign UUID
        merged["stakeholder_id"] = str(uuid.uuid4())
        results.append(merged)

    return results


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[deduplicator] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    stakeholders = json.loads(INPUT_PATH.read_text())
    before = len(stakeholders)
    deduped = deduplicate(stakeholders)
    after = len(deduped)

    OUTPUT_PATH.write_text(json.dumps(deduped, indent=2, default=str))
    print(
        f"[deduplicator] {before} → {after} stakeholders "
        f"({before - after} merged) → {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
