# City Scraper — Real Estate Stakeholder Intelligence Pipeline
## Design Plan & Reference Document

---

## The Problem

Identifying all key decision-makers tied to a property — developer, architect, lender, GC, subcontractors — currently requires manual lookup across a dozen fragmented data sources. Each source covers a different slice of the stakeholder picture, and false positives are rampant without cross-verification.

---

## The Solution

A Python automation pipeline that takes **a property address + ZIP code** as input and outputs a **structured Google Sheet** containing every key stakeholder with:
- Name, company, phone, email, LinkedIn
- Their verified role (Developer / Architect / GC / Subcontractor / Lender / Owner)
- A confidence score (0–100) based on source authority, recency, and cross-match
- Data provenance (which sources confirmed them)
- Flags for anything requiring human review

---

## Architecture (3-Layer Model)

Following the project's `CLAUDE.md` architecture:

```
Layer 1 — Directive (What to do)
  directives/*.md   — SOPs in plain language, living documents

Layer 2 — Orchestration (Decision making)
  AI agent reads directives, calls execution scripts in order,
  handles errors, self-anneals when things break

Layer 3 — Execution (Doing the work)
  execution/*.py    — Deterministic Python scripts
  .env              — API keys (never hardcoded)
  credentials.json  — Google service account key (you add this)
  .tmp/             — Intermediate files (ephemeral, regenerated per run)
```

**Why this works:** Each script has one job, one input file, one output file.
If a source fails, the pipeline degrades gracefully — it never crashes entirely.

---

## API Stack

Six data sources, chosen for maximum stakeholder coverage with minimum overlap:

| # | Source | What it returns | Cost | Status |
|---|--------|----------------|------|--------|
| 1 | **Smarty US Street** | USPS-verified address, county FIPS, lat/lon | Free 250/mo | Required first — normalizes address |
| 2 | **Shovels.ai** | Permit applicants, contractor names, emails, phones, license data | $599/mo | Primary — permits surface developer, GC, architect, subs |
| 3 | **ATTOM Data Solutions** | Property owner, lender name, loan amount, deed history | ~$95/mo | Cross-verifies ownership, adds lender |
| 4 | **OpenCorporates** | LLC officers, registered agent, incorporation info | Free 200/mo | Pierces LLCs to find human decision-makers |
| 5 | **Apollo.io** | Email, phone, LinkedIn by name + company | Free 100 credits/mo | Contact enrichment |
| 6 | **Hunter.io** | Email search by company domain | Free 50/mo | Email fallback when Apollo fails |

**County Assessor APIs** — Free for ~200 major US counties (LA, Cook, Harris, King, NYC, etc.)
Additional cross-reference for ownership data. Graceful skip for unsupported counties.

### Sources Excluded and Why

| Source | Reason Excluded |
|--------|----------------|
| CoStar / Reonomy | $15K+/yr, no self-serve API |
| BuildZoom | Narrower than Shovels, TOS risk |
| PermitData.io | Does not exist as a product (Shovels is the equivalent) |
| Melissa Data | Fully overlaps with Smarty |
| SOS APIs directly | OpenCorporates already aggregates 130+ jurisdictions |

### Source Independence Matrix

Critical for cross-verification logic. Sources in the same group count as ONE, not two:

| Source | Group |
|--------|-------|
| Shovels | `permit` |
| ATTOM | `deed` |
| County Assessor | `deed` (same lineage as ATTOM) |
| OpenCorporates | `sos` |
| Apollo | `contact_db` |
| Hunter | `contact_db` (same lineage as Apollo) |

**Independent pairs:** Shovels + ATTOM ✓ | Shovels + OpenCorporates ✓ | ATTOM + OpenCorporates ✓
**Not independent:** ATTOM + County Assessor ✗ | Apollo + Hunter ✗

---

## Pipeline Stages

```
INPUT: address (str) + zip_code (str)
         │
         ▼
  Stage 0: normalize_address.py
  └─ Smarty API → StandardAddress → .tmp/normalized_address.json
  └─ STOP if DPV match code = "N" (undeliverable)
         │
         ▼
  Stage 1: Parallel API fan-out (asyncio.gather)
  ├─ Task A:  shovels_permit_fetch.py     → .tmp/shovels_permits.json
  ├─ Task A2: shovels_contractor_fetch.py → .tmp/shovels_contractors.json
  ├─ Task B:  attom_property_fetch.py     → .tmp/attom_property.json
  ├─ Task C:  opencorporates_entity_lookup.py → .tmp/opencorporates_entities.json
  └─ Task D:  county_assessor_fetch.py    → .tmp/county_assessor.json
         │
         ▼
  Stage 2: entity_extractor.py
  └─ Reads all .tmp/* → classifies roles → .tmp/stakeholder_candidates.json
         │
         ▼
  Stage 3: contact_enricher.py
  └─ Apollo + Hunter per candidate → .tmp/enriched_stakeholders.json
         │
         ▼
  Stage 4: cross_verifier.py
  └─ Counts independent sources → flags SINGLE_SOURCE → .tmp/verified_stakeholders.json
         │
         ▼
  Stage 5: confidence_scorer.py
  └─ Scores 0-100 → labels Verified/Probable/Unconfirmed → .tmp/scored_stakeholders.json
         │
         ▼
  Stage 6: deduplicator.py
  └─ Merges duplicates (phone/email/LinkedIn/fuzzy name) → .tmp/final_stakeholders.json
         │
         ▼
  Stage 7: sheets_writer.py
  └─ Writes to Google Sheet tab "{AddressSlug}_{YYYY-MM-DD}"

OUTPUT: Google Sheet URL
```

### Role Classification Logic

| Signal | Role |
|--------|------|
| ATTOM `lender_name` | Lender |
| ATTOM / Assessor `owner_name` | Owner |
| Shovels `classification_derived` contains "architect" | Architect |
| Shovels `classification_derived` contains "general" | GC |
| Shovels `classification_derived` contains "electrical/plumbing/hvac/..." | Subcontractor |
| Permit `applicant_name` ≠ ATTOM deed owner | Developer (probable) |
| OpenCorporates officer, position "manager/president/ceo" | Developer |

---

## Confidence Scoring Formula

```
confidence_score = min(source_score + cross_bonus + contact_bonus, 100)
```

### Source Score (0–60 points)
```
source_score = Σ( W[source] × D[recency] × 100 ), capped at 60
```

Authority weights:
| Source | Weight |
|--------|--------|
| Shovels (government permit) | 0.30 |
| ATTOM (recorded deed) | 0.28 |
| County Assessor (tax authority) | 0.22 |
| OpenCorporates (SOS filing) | 0.20 |
| Apollo / Hunter (commercial DB) | 0.10 |
| Web / Exa search | 0.05 |

Recency decay: `D = max(0.30, 1.0 − (years_old × 0.14))`
Examples: fresh→1.0, 1yr→0.86, 3yr→0.58, 5yr→0.30 (floor)

### Cross-Match Bonus (0–30 points)
| Independent sources | Bonus |
|--------------------|-------|
| 1 | +0 |
| 2 | +15 |
| 3 | +25 |
| 4+ | +30 |

### Contact Completeness (0–10 points)
Email +5 | Phone +5 | LinkedIn +3 | Max 10

### Label Thresholds
| Score | Label |
|-------|-------|
| 75–100 | **Verified** |
| 45–74 | **Probable** |
| 0–44 | **Unconfirmed** |

---

## Google Sheet Column Structure

Tab name: `{AddressSlug}_{YYYY-MM-DD}` e.g. `350FifthAveNY_2026-04-09`

| Col | Header | Source |
|-----|--------|--------|
| A | Stakeholder ID | Generated UUID |
| B | Role | entity_extractor |
| C | Full Name | Primary source |
| D | Company | Primary source |
| E | Phone (E.164) | Shovels / Apollo |
| F | Email | Shovels / Apollo / Hunter |
| G | LinkedIn URL | Shovels / Apollo |
| H | Confidence Score (0–100) | confidence_scorer |
| I | Confidence Label | confidence_scorer |
| J | Independent Sources (count) | cross_verifier |
| K | Source List (pipe-delimited) | cross_verifier |
| L | Source Details (JSON) | All stages |
| M | Permit Number | Shovels |
| N | Permit Date | Shovels |
| O | Permit Type | Shovels |
| P | Permit Value (USD) | Shovels |
| Q | License Number | Shovels |
| R | License Status | Shovels |
| S | License Expiry | Shovels |
| T | Property Address | normalize_address |
| U | County FIPS | normalize_address |
| V | ATTOM Lender | ATTOM |
| W | ATTOM Loan Amount | ATTOM |
| X | Last Verified Date | pipeline_runner |
| Y | Notes / Flags | cross_verifier |
| Z | Raw Data Path | pipeline_runner |

Formatting: Row 1 frozen. Column H conditional (green ≥75, yellow 45–74, red <45). Auto-filter all.

**Column Y Flag values:**
`SINGLE_SOURCE` | `LICENSE_EXPIRED` | `LLC_UNRESOLVED` | `NO_PERMIT_DATA` | `ARCHITECT_WEB_ONLY` | `SUB_INFERRED` | `ENRICHMENT_SKIPPED`

---

## Known Gaps and Decisions Required

### Budget (Blocking Decision)
Minimum monthly cost for production: **~$800/mo**
- Shovels: $599/mo
- ATTOM: ~$95/mo
- Apollo: $59/mo
- Hunter: $49/mo

If budget-constrained: prioritize Shovels over ATTOM. Pipeline degrades gracefully (loses lender data and deed cross-verification).

### Data Gaps (By Design — Cannot Be Fully Automated)

| Gap | Reason | Mitigation |
|-----|--------|-----------|
| Architect | Named in PDF plan sets, not structured permit fields | Exa web search fallback → flagged `ARCHITECT_WEB_ONLY` |
| Subcontractors | Not named on main permit | Inferred from specialty sub-permits → flagged `SUB_INFERRED` |
| Private lenders | No deed of trust recorded for hard money loans | No mitigation from public data |

### OpenCorporates Volume Limit
Free tier = 200 req/mo → ~8–10 full property runs/month.
Commercial license: ~$2,800/yr. Defer until volume demands it.

### Apollo Credit Conservation
Phone reveals = 5 credits each. Capped to Developer + GC roles only via `ENRICH_PHONE_ROLES` env var.

### Legal / TOS Constraints
- Shovels: internal use only, no resale
- Apollo/Hunter: no bulk cold outreach with the output
- OpenCorporates free tier: non-commercial use only
- CCPA: delete Google Sheet rows older than 12 months

---

## File Structure

```
city_scraper/
├── PLAN.md                          ← This document
├── README.md                        ← Quick start guide
├── .env                             ← API keys (fill in)
├── credentials.json                 ← Google service account (you add)
├── requirements.txt                 ← Python dependencies
├── .tmp/                            ← Intermediate files (auto-generated, gitignore)
│   ├── normalized_address.json
│   ├── shovels_permits.json
│   ├── shovels_contractors.json
│   ├── attom_property.json
│   ├── opencorporates_entities.json
│   ├── county_assessor.json
│   ├── stakeholder_candidates.json
│   ├── enriched_stakeholders.json
│   ├── verified_stakeholders.json
│   ├── scored_stakeholders.json
│   ├── final_stakeholders.json
│   ├── api_calls.log
│   └── run_summary.json
├── execution/                       ← All Python scripts (Layer 3)
│   ├── models.py                    ← Shared dataclasses (schema contract)
│   ├── api_client.py                ← Async HTTP, rate limiting, backoff
│   ├── normalize_address.py         ← Stage 0: Smarty address verification
│   ├── shovels_permit_fetch.py      ← Stage 1A: Permits
│   ├── shovels_contractor_fetch.py  ← Stage 1A: Contractor profiles
│   ├── attom_property_fetch.py      ← Stage 1B: Owner + lender
│   ├── opencorporates_entity_lookup.py ← Stage 1C: LLC officers
│   ├── county_assessor_router.py    ← Stage 1D: County → API config
│   ├── county_assessor_fetch.py     ← Stage 1D: County assessor fetch
│   ├── entity_extractor.py          ← Stage 2: Role classification
│   ├── contact_enricher.py          ← Stage 3: Apollo + Hunter
│   ├── cross_verifier.py            ← Stage 4: Independence check
│   ├── confidence_scorer.py         ← Stage 5: Scoring algorithm
│   ├── deduplicator.py              ← Stage 6: Merge duplicates
│   ├── sheets_writer.py             ← Stage 7: Google Sheets write
│   └── pipeline_runner.py           ← Orchestrator entry point
└── directives/                      ← All SOPs (Layer 1)
    ├── 01_stakeholder_pipeline_overview.md
    ├── 02_address_normalization.md
    ├── 03_data_sources_and_api_keys.md
    ├── 04_permit_and_contractor_extraction.md
    ├── 05_entity_resolution_and_roles.md
    ├── 06_contact_enrichment.md
    ├── 07_confidence_scoring.md
    ├── 08_deduplication.md
    ├── 09_google_sheets_output.md
    ├── 10_error_handling_and_retry.md
    └── 11_tmp_directory_and_cache.md
```

---

## Session Log

| Date | What Was Done |
|------|---------------|
| 2026-04-08 | Full system designed: API stack selected, pipeline architecture designed, confidence scoring formula defined, Google Sheet schema defined |
| 2026-04-09 | All 16 execution scripts built and tested (pipeline runs, fails cleanly at Stage 0 awaiting API keys). All 11 directives written. Project organized into city_scraper/ |

---

## Next Steps

1. Add API keys to `.env`
2. Add `credentials.json` (Google service account)
3. Run: `python3 execution/pipeline_runner.py --address "YOUR ADDRESS" --zip "ZIPCODE"`
4. Add future scraper modules (e.g., city permit portal scrapers) as new `execution/` scripts + `directives/` SOPs
