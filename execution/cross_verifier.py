"""
Stage 4: Cross-Verification

For each enriched stakeholder, counts how many INDEPENDENT source groups
have contributed data. Uses the independence matrix from models.py.

A stakeholder is "cross_verified" if independent_source_count >= 2.
Single-source stakeholders are flagged but NOT excluded.

Input:  .tmp/enriched_stakeholders.json
Output: .tmp/verified_stakeholders.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from models import INDEPENDENT_SOURCE_GROUPS

INPUT_PATH = Path(__file__).parent.parent / ".tmp" / "enriched_stakeholders.json"
OUTPUT_PATH = Path(__file__).parent.parent / ".tmp" / "verified_stakeholders.json"


def count_independent_sources(source_records: list[dict[str, Any]]) -> int:
    """
    Return the number of independent data lineages represented.
    Sources in the same group (e.g., ATTOM + CountyAssessor = 'deed') count as 1.
    """
    groups: set[str] = set()
    for ref in source_records:
        source_name = ref.get("source_name", "")
        group = INDEPENDENT_SOURCE_GROUPS.get(source_name, source_name)
        groups.add(group)
    return len(groups)


def verify(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    verified = []
    for c in candidates:
        source_records = c.get("source_records", [])
        independent_count = count_independent_sources(source_records)

        status = "cross_verified" if independent_count >= 2 else "single_source"

        # Build source group summary for transparency
        groups: dict[str, list[str]] = {}
        for ref in source_records:
            sn = ref.get("source_name", "")
            group = INDEPENDENT_SOURCE_GROUPS.get(sn, sn)
            groups.setdefault(group, []).append(sn)

        row = dict(c)
        row["verification_status"] = status
        row["independent_source_count"] = independent_count
        row["source_groups"] = groups

        # Update flags
        flags = list(row.get("flags", []))
        if status == "single_source" and "SINGLE_SOURCE" not in flags:
            flags.append("SINGLE_SOURCE")
        row["flags"] = flags

        verified.append(row)
    return verified


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INPUT_PATH.exists():
        print(f"[cross_verifier] ERROR: {INPUT_PATH} not found", file=sys.stderr)
        sys.exit(1)

    candidates = json.loads(INPUT_PATH.read_text())
    verified = verify(candidates)

    cross = sum(1 for v in verified if v["verification_status"] == "cross_verified")
    single = len(verified) - cross

    OUTPUT_PATH.write_text(json.dumps(verified, indent=2, default=str))
    print(
        f"[cross_verifier] {cross} cross-verified, {single} single-source "
        f"→ {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
