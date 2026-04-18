"""
Stage 5: Confidence Scoring

Computes a 0-100 confidence score for each stakeholder based on:
  - Source authority weights (government records > commercial DBs)
  - Recency decay (data older than 5 years floors at 0.30 multiplier)
  - Cross-match bonus (up to +30 for 4+ independent sources)
  - Contact completeness bonus (up to +10 for email + phone + LinkedIn)

Score → Label:
  75-100 = Verified
  45-74  = Probable
  0-44   = Unconfirmed

Input:  .tmp/verified_stakeholders.json
Output: .tmp/scored_stakeholders.json
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "verified_stakeholders.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "scored_stakeholders.json"

# ── Source authority weights ───────────────────────────────────────────────────
SOURCE_WEIGHTS: dict[str, float] = {
    "Shovels": 0.30,           # government-filed permit (highest authority)
    "ATTOM": 0.28,             # recorded deed / mortgage instrument
    "CountyAssessor": 0.22,    # tax authority record
    "OpenCorporates": 0.20,    # Secretary of State filing
    "Apollo": 0.10,            # commercial contact database
    "Hunter": 0.10,            # commercial contact database
    "Exa": 0.05,               # unstructured web
}
DEFAULT_WEIGHT = 0.05


def recency_decay(record_date_str: str | None, today: date | None = None) -> float:
    """
    Returns 1.0 (fresh) → 0.30 (stale, floored).
    Linear decay: loses 0.14 per year, floored at 0.30.
    """
    if not record_date_str:
        return 0.5   # unknown date — moderate penalty
    if today is None:
        today = date.today()
    try:
        record_date = date.fromisoformat(str(record_date_str)[:10])
    except ValueError:
        return 0.5
    years_old = (today - record_date).days / 365.25
    return max(0.30, 1.0 - (years_old * 0.14))


def cross_match_bonus(independent_source_count: int) -> float:
    """Bonus for appearing in multiple independent data lineages."""
    bonuses = {0: 0.0, 1: 0.0, 2: 15.0, 3: 25.0}
    return bonuses.get(min(independent_source_count, 3), 30.0)


def contact_completeness_bonus(stakeholder: dict[str, Any]) -> float:
    """Up to +10 points for having email, phone, LinkedIn."""
    score = 0.0
    if stakeholder.get("email"):
        score += 5.0
    if stakeholder.get("phone"):
        score += 5.0
    if stakeholder.get("linkedin_url"):
        score += 3.0
    return min(score, 10.0)


def compute_score(stakeholder: dict[str, Any], today: date | None = None) -> float:
    """
    Returns a confidence score 0.0–100.0.

    source_score   = sum(W[source] × D[recency] × 100), capped at 60
    cross_bonus    = {1:0, 2:15, 3:25, 4+:30}
    contact_bonus  = email(+5) + phone(+5) + linkedin(+3), capped at 10
    total          = min(source_score + cross_bonus + contact_bonus, 100)
    """
    if today is None:
        today = date.today()

    source_records = stakeholder.get("source_records", [])
    independent_count = stakeholder.get("independent_source_count", 1)

    # Source authority × recency
    source_score = 0.0
    for ref in source_records:
        source_name = ref.get("source_name", "")
        weight = SOURCE_WEIGHTS.get(source_name, DEFAULT_WEIGHT)
        decay = recency_decay(ref.get("record_date"), today)
        source_score += weight * decay * 100

    source_score = min(source_score, 60.0)

    cross = cross_match_bonus(independent_count)
    contact = contact_completeness_bonus(stakeholder)

    return round(min(source_score + cross + contact, 100.0), 1)


def score_to_label(score: float) -> str:
    if score >= 75:
        return "Verified"
    if score >= 45:
        return "Probable"
    return "Unconfirmed"


def score_all(stakeholders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = date.today()
    scored = []
    for s in stakeholders:
        score = compute_score(s, today)
        row = dict(s)
        row["confidence_score"] = score
        row["confidence_label"] = score_to_label(score)
        scored.append(row)
    return scored


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[confidence_scorer] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    stakeholders = json.loads(INPUT_PATH.read_text())
    scored = score_all(stakeholders)

    label_counts = {"Verified": 0, "Probable": 0, "Unconfirmed": 0}
    for s in scored:
        label_counts[s["confidence_label"]] += 1

    OUTPUT_PATH.write_text(json.dumps(scored, indent=2, default=str))
    print(
        f"[confidence_scorer] Scored {len(scored)}: "
        f"Verified={label_counts['Verified']}, "
        f"Probable={label_counts['Probable']}, "
        f"Unconfirmed={label_counts['Unconfirmed']} → {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
