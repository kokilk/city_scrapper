"""
Pipeline Runner — Prototype Orchestrator

Stages:
  0. normalize_address    (Smarty — required)
  1. permit_scraper       (NYC DOB or generic — free, no key)
     pluto_lookup         (NYC PLUTO owner — free, no key)   [parallel with permits]
  2. entity_extractor     (role classification)
  3. web_enricher         (Exa + Google CSE — website, email, phone)
  4. contact_enricher     (Apollo + Hunter — LinkedIn, email gap-fill)
  5. cross_verifier       (count independent sources)
  6. confidence_scorer    (0–100 score)
  7. deduplicator         (merge duplicates)
  8. sheets_writer        (Google Sheet output)

Usage:
  python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118"
  python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118" --skip-sheets
  python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118" --no-cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

BASE = Path(__file__).parent.parent
TMP = BASE / ".tmp"
CACHE_TTL_HOURS = 24


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < CACHE_TTL_HOURS * 3600


def _run_script(script_name: str) -> bool:
    script_path = Path(__file__).parent / script_name
    print(f"\n{'─'*60}")
    print(f"▶ {script_name}")
    print(f"{'─'*60}")
    result = subprocess.run([sys.executable, str(script_path)], capture_output=False)
    if result.returncode != 0:
        print(f"✗ {script_name} failed (exit {result.returncode})", file=sys.stderr)
        return False
    return True


async def _run_parallel(scripts: list[str]) -> dict[str, bool]:
    """Run multiple scripts concurrently."""
    async def run_one(script: str) -> tuple[str, bool]:
        script_path = Path(__file__).parent / script
        print(f"  ↳ Starting {script}")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            print(stdout.decode(), end="")
        if stderr:
            print(stderr.decode(), end="", file=sys.stderr)
        ok = proc.returncode == 0
        print(f"  {'✓' if ok else '✗'} {script} (exit {proc.returncode})")
        return script, ok

    print(f"\n{'─'*60}")
    print("▶ Stage 1: Parallel data fetch")
    print(f"{'─'*60}")
    results = await asyncio.gather(*[run_one(s) for s in scripts])
    return dict(results)


def _load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return default
    return default


def _write_run_summary(
    address: str,
    zip_code: str,
    start_time: float,
    stakeholders: list[dict],
    sheet_url: str,
    source_statuses: dict[str, str],
) -> None:
    label_counts = {"Verified": 0, "Probable": 0, "Unconfirmed": 0}
    for s in stakeholders:
        label = s.get("confidence_label", "Unconfirmed")
        label_counts[label] = label_counts.get(label, 0) + 1

    summary = {
        "run_timestamp": datetime.now().isoformat(),
        "address": address,
        "zip": zip_code,
        "duration_seconds": round(time.time() - start_time, 1),
        "stakeholders_total": len(stakeholders),
        "verified": label_counts["Verified"],
        "probable": label_counts["Probable"],
        "unconfirmed": label_counts["Unconfirmed"],
        "sheet_url": sheet_url,
        "source_statuses": source_statuses,
    }
    (TMP / "run_summary.json").write_text(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Real Estate Stakeholder Pipeline")
    parser.add_argument("--address", required=True, help="Street address e.g. '350 5th Ave'")
    parser.add_argument("--zip", required=True, dest="zip_code", help="ZIP code e.g. '10118'")
    parser.add_argument("--no-cache", action="store_true", help="Force re-fetch all data")
    args = parser.parse_args()

    start_time = time.time()
    TMP.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, str] = {}

    print(f"\n{'='*60}")
    print(f"  STAKEHOLDER INTELLIGENCE PIPELINE")
    print(f"  Address: {args.address}, {args.zip_code}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ── Stage 0: Address normalization ───────────────────────────────────────
    addr_path = TMP / "normalized_address.json"
    if args.no_cache or not _is_fresh(addr_path):
        print(f"\n{'─'*60}")
        print("▶ Stage 0: Address normalization")
        print(f"{'─'*60}")
        try:
            from dotenv import load_dotenv
            from dataclasses import asdict
            load_dotenv()
            from normalize_address import normalize
            addr = normalize(args.address, args.zip_code)
            addr_path.write_text(json.dumps(asdict(addr), indent=2, default=str))
            print(f"[normalize] ✓ {addr.full()} (DPV={addr.dpv_match_code})")
            statuses["normalize"] = "ok"
        except Exception as exc:
            print(f"\n[pipeline] FATAL: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"\n[pipeline] Using cached address ({addr_path.name})")
        statuses["normalize"] = "cached"

    # ── Stage 1: Parallel data fetch ─────────────────────────────────────────
    permits_path = TMP / "permits.json"
    pluto_path = TMP / "pluto_owner.json"

    if args.no_cache or not all(_is_fresh(p) for p in [permits_path, pluto_path]):
        stage1 = asyncio.run(_run_parallel(["permit_scraper.py", "pluto_lookup.py"]))
        statuses["permits"] = "ok" if stage1.get("permit_scraper.py") else "failed"
        statuses["pluto"] = "ok" if stage1.get("pluto_lookup.py") else "failed"

        # OpenCorporates (optional, free 200/mo)
        if _run_script("opencorporates_entity_lookup.py"):
            statuses["opencorporates"] = "ok"
        else:
            statuses["opencorporates"] = "skipped"
    else:
        print("\n[pipeline] Using cached Stage 1 data (< 24h old). Use --no-cache to refresh.")
        for k in ["permits", "pluto", "opencorporates"]:
            statuses[k] = "cached"

    # ── Stage 2: Entity extraction ────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("▶ Stage 2: Entity extraction")
    print(f"{'─'*60}")
    if not _run_script("entity_extractor.py"):
        print("[pipeline] WARNING: Entity extraction failed", file=sys.stderr)
        statuses["entity_extractor"] = "failed"
    else:
        statuses["entity_extractor"] = "ok"

    # ── Stage 3: Web enrichment (Exa + Google CSE) ────────────────────────────
    print(f"\n{'─'*60}")
    print("▶ Stage 3: Web enrichment (Exa + Google CSE)")
    print(f"{'─'*60}")
    if not _run_script("web_enricher.py"):
        print("[pipeline] WARNING: Web enrichment failed — copying candidates as fallback", file=sys.stderr)
        statuses["web_enricher"] = "failed"
        # Fallback: copy candidates to web_enriched so next stage can proceed
        cand = TMP / "stakeholder_candidates.json"
        web = TMP / "web_enriched.json"
        if cand.exists() and not web.exists():
            web.write_text(cand.read_text())
    else:
        statuses["web_enricher"] = "ok"

    # ── Stage 4: Contact enrichment (Apollo + Hunter for LinkedIn/email gaps) ─
    print(f"\n{'─'*60}")
    print("▶ Stage 4: Contact enrichment (Apollo + Hunter)")
    print(f"{'─'*60}")
    if not _run_script("contact_enricher.py"):
        print("[pipeline] WARNING: Contact enrichment failed — continuing without it", file=sys.stderr)
        statuses["contact_enricher"] = "failed"
        web = TMP / "web_enriched.json"
        enrich = TMP / "enriched_stakeholders.json"
        if web.exists() and not enrich.exists():
            enrich.write_text(web.read_text())
    else:
        statuses["contact_enricher"] = "ok"

    # ── Stage 5: Cross-verification ───────────────────────────────────────────
    _run_script("cross_verifier.py")

    # ── Stage 6: Confidence scoring ───────────────────────────────────────────
    _run_script("confidence_scorer.py")

    # ── Stage 7: Deduplication ────────────────────────────────────────────────
    _run_script("deduplicator.py")

    # ── Stage 8: Export JSON (for n8n → Google Sheets) ───────────────────────
    if _run_script("export_json.py"):
        statuses["export_json"] = "ok"
    else:
        statuses["export_json"] = "failed"

    sheet_url = ""

    # ── Summary ───────────────────────────────────────────────────────────────
    final = _load_json(TMP / "final_stakeholders.json", [])
    label_counts = {"Verified": 0, "Probable": 0, "Unconfirmed": 0}
    for s in final:
        lbl = s.get("confidence_label", "Unconfirmed")
        label_counts[lbl] = label_counts.get(lbl, 0) + 1

    _write_run_summary(args.address, args.zip_code, start_time, final, sheet_url, statuses)

    elapsed = round(time.time() - start_time, 1)
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE ({elapsed}s)")
    print(f"  Stakeholders found: {len(final)}")
    print(f"    ✓ Verified:     {label_counts['Verified']}")
    print(f"    ~ Probable:     {label_counts['Probable']}")
    print(f"    ? Unconfirmed:  {label_counts['Unconfirmed']}")
    if sheet_url:
        print(f"  Sheet: {sheet_url}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
