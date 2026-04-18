# Directive 01: Stakeholder Pipeline Overview

## Purpose
Run this pipeline when given a property address and ZIP code to produce a Google Sheet of all key stakeholders: developer, architect, lender, GC, subcontractors, and owners — with verified contact information and confidence scores.

## When to Invoke
- User provides a property address and ZIP code and asks for stakeholder discovery
- User says "run the pipeline", "find the stakeholders", "who's involved in this project"

## Entry Point

```bash
python execution/pipeline_runner.py --address "ADDRESS" --zip "ZIPCODE"
```

Optional flags:
- `--no-cache` — Force fresh data fetch (ignore cached .tmp/ files)
- `--skip-sheets` — Run all stages but skip Google Sheet write (useful for testing)

## Input Contract
- Raw street address (any format — Smarty will normalize it)
- ZIP code (5-digit)

## Output Contract
- Google Sheet tab named `{AddressSlug}_{YYYY-MM-DD}` in the spreadsheet at `GOOGLE_SHEET_ID`
- `.tmp/final_stakeholders.json` — machine-readable final output
- `.tmp/run_summary.json` — execution summary with timings and source statuses

## Prerequisites (check before running)
1. All API keys set in `.env` (see `directives/03_data_sources_and_api_keys.md`)
2. `credentials.json` exists in the project root (Google service account key)
3. Python dependencies installed: `pip install -r requirements.txt`
4. Target Google Sheet exists and is shared with the service account email

## What the Pipeline Does

| Stage | Script | Description |
|-------|--------|-------------|
| 0 | `normalize_address.py` | USPS-verify address via Smarty |
| 1A | `shovels_permit_fetch.py` | Fetch all permits from Shovels.ai |
| 1A2 | `shovels_contractor_fetch.py` | Fetch contractor profiles for each permit |
| 1B | `attom_property_fetch.py` | Fetch owner + lender from ATTOM |
| 1C | `opencorporates_entity_lookup.py` | Resolve LLC entities to officers |
| 1D | `county_assessor_fetch.py` | Fetch owner from county assessor (where available) |
| 2 | `entity_extractor.py` | Classify stakeholders by role |
| 3 | `contact_enricher.py` | Enrich with email/phone/LinkedIn via Apollo + Hunter |
| 4 | `cross_verifier.py` | Check data appears in ≥2 independent sources |
| 5 | `confidence_scorer.py` | Score 0-100 by authority, recency, cross-match |
| 6 | `deduplicator.py` | Merge duplicate records |
| 7 | `sheets_writer.py` | Write to Google Sheet |

## Success Criteria
- Pipeline completes without fatal errors
- At least 1 stakeholder with confidence_label = "Verified" in the output
- Google Sheet tab created/updated with correct headers
- `.tmp/run_summary.json` written with elapsed time < 300 seconds

## Failure Handling
- If Stage 0 fails (undeliverable address): stop, ask user to verify the address
- If Stage 1 sources fail individually: log as FAILED, continue to next stage
- If ALL Stage 1 sources fail: stop and report — no useful output is possible
- If Stage 7 (sheets) fails: still report success for data collection; ask user to check credentials.json

## Self-Annealing Protocol
If a Stage 1 script returns unexpected API fields or errors:
1. Read the error and the raw response in `.tmp/api_calls.log`
2. Fix the parsing in the relevant execution script
3. Re-run with `--no-cache` to re-test with live data
4. Update this directive with any newly discovered field name changes
