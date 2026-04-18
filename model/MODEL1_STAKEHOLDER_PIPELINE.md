# Model 1 — Full Stakeholder Pipeline

The original, deep-research pipeline. Given a building address, it identifies **every key stakeholder role** connected to that property, cross-verifies each one across multiple sources, and outputs a scored, deduplicated record set.

---

## What It Finds

For each building address, Model 1 identifies:

| Role | Example |
|------|---------|
| **Owner** | Waterbridge Capital LLC (Joel Schreiber) |
| **Developer** | Atlas Capital Group (Jeffrey Goldberger, Andrew Cohen) |
| **Architect** | MdeAS Architects (Dan Shannon) |
| **General Contractor** | Schimenti Construction (Matthew Schimenti) |
| **Subcontractor** | Sweet Group LLC (Jerry Botti) |
| **Lender** | Bank of America ($425M loan) |
| **Leasing Agent** | Cushman & Wakefield (Jon Fales) |

---

## Output Format

**CSV columns (15):**

| Column | Description |
|--------|-------------|
| `property_address` | Normalized full address |
| `role` | Owner / Developer / Architect / GC / Lender / Leasing Agent |
| `full_name` | Person's name (empty if only company identified) |
| `company` | Company name |
| `phone` | Direct phone number |
| `email` | Verified email address |
| `linkedin_url` | LinkedIn profile URL |
| `website` | Company website |
| `confidence_score` | 0–100 numeric score |
| `confidence_label` | Verified / Probable / Unconfirmed |
| `sources` | Which APIs confirmed this record |
| `permit_number` | DOB permit number (if applicable) |
| `permit_type` | Permit type classification |
| `notes` | Full research notes, methodology, VERIFY flags |
| `linkedin_headline` | Person's LinkedIn headline |

**Output files:**
- `output/LIC_all_stakeholders_FINAL.csv` — combined all addresses
- Google Sheet (tab per address run)

---

## Confidence Scoring

Each stakeholder gets a 0–100 score based on:

| Score Range | Label | Meaning |
|-------------|-------|---------|
| 75–100 | **Verified** | Confirmed by 2+ independent sources |
| 45–74 | **Probable** | Single strong source, no contradictions |
| 0–44 | **Unconfirmed** | Found in one source, not cross-verified |

Score components:
- Source authority (government deed = highest, web scrape = lowest)
- Number of independent sources confirming
- Recency of the data
- Contact information completeness

Flags added to notes:
- `VERIFY_LINKEDIN` — LinkedIn match is approximate, not confirmed
- `SINGLE_SOURCE` — only one source found this person
- `LICENSE_EXPIRED` — contractor license lapsed
- `LLC_UNRESOLVED` — holding LLC, no human officer found

---

## Pipeline Stages

```
Address Input
    │
    ▼
Stage 0: normalize_address.py
    Smarty Streets → standardized address, ZIP+4, DPV confirmation
    │
    ▼
Stage 1 (parallel):
    ├── pluto_lookup.py         NYC PLUTO → owner LLC, block/lot, building class
    ├── permit_scraper.py       NYC DOB → active permits, job applicants
    ├── shovels_permit_fetch.py Shovels → permit history + contractor names
    ├── shovels_contractor_fetch.py Shovels → contractor profiles (email, phone, license)
    ├── attom_property_fetch.py ATTOM → deed owner, lender, sale history
    ├── opencorporates_entity_lookup.py OpenCorporates → LLC officers
    └── county_assessor_fetch.py County records (backup)
    │
    ▼
Stage 2: entity_extractor.py
    Classify raw records into stakeholder roles
    │
    ▼
Stage 3: web_enricher.py
    Exa + Google CSE → company website, team page, web mentions
    │
    ▼
Stage 4: contact_enricher.py
    Apollo.io → email + phone + LinkedIn (primary)
    Hunter.io → email fallback
    │
    ▼
Stage 5: cross_verifier.py
    Count independent sources per stakeholder
    Flag single-source records
    │
    ▼
Stage 6: confidence_scorer.py
    Assign 0–100 score + label
    │
    ▼
Stage 7: deduplicator.py
    Merge duplicate people / companies
    │
    ▼
Stage 8: sheets_writer.py
    Write to Google Sheet → print URL
```

---

## APIs Used

| API | What it provides | Free Tier | Paid |
|-----|-----------------|-----------|------|
| **Smarty Streets** | Address normalization, DPV validation | 250 lookups/mo | Yes |
| **NYC PLUTO** | Owner LLC, building class, assessed value | Unlimited (free) | — |
| **NYC DOB** | Permit history, job applicants, contractor IDs | Unlimited (free) | — |
| **Shovels.ai** | Permit data + contractor profiles with contact info | None | $599/mo |
| **ATTOM Data** | Deed owner, lender, mortgage amount, sale date | None | ~$95/mo |
| **OpenCorporates** | LLC officer names, incorporation data, registered agents | 200 req/mo | Yes |
| **Apollo.io** | Email, phone, LinkedIn, title, seniority | 100 credits/mo | Yes |
| **Hunter.io** | Email discovery by domain | 50 searches/mo | Yes |
| **Google Sheets API** | Output destination | Free | — |

### Source Independence Matrix

These source pairs are **independent** (safe to cross-verify):
- Shovels + ATTOM (permit DB vs deed record)
- Shovels + OpenCorporates (permit vs SOS filing)
- ATTOM + OpenCorporates (deed vs SOS filing)
- Any government source + Apollo/Hunter

These pairs are **NOT independent** (same data lineage):
- ATTOM + County Assessor (both from deed/tax records)
- Apollo + Hunter (both commercial contact databases)

---

## Running Model 1

```bash
# Single address
python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118"

# Dry run (skip Google Sheets write)
python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118" --skip-sheets

# Force re-fetch (ignore 24h cache)
python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118" --no-cache
```

**Intermediate files** are cached in `.tmp/` for 24 hours so re-runs skip completed stages.

---

## Required Environment Variables

```env
SMARTY_AUTH_ID=
SMARTY_AUTH_TOKEN=
SHOVELS_API_KEY=
ATTOM_API_KEY=
OPENCORPORATES_API_KEY=
APOLLO_API_KEY=
HUNTER_API_KEY=
GOOGLE_SHEET_ID=
ENRICH_PHONE_ROLES=Developer,GC
```

Also requires `credentials.json` (Google service account) in project root.

See [Directive 03](directives/03_data_sources_and_api_keys.md) for full setup instructions.

---

## Known Limitations

- **Shell LLCs / SPEs**: Holding companies with no public leadership are marked `LLC_UNRESOLVED`. Fix: add OpenCorporates paid tier or NYC ACRIS deed search.
- **DOB permit API timeouts**: NYC DOB BIS portal occasionally times out. Notes include manual lookup URL.
- **Contractor GC gaps**: If a building has no active permits, GC cannot be identified from DOB.
- **LinkedIn matching**: URL search returns approximate matches — all flagged `VERIFY_LINKEDIN`.

---

## Sample Output

From `output/LIC_all_stakeholders_FINAL.csv` — 28-07 Jackson Avenue (The JACX):

| Role | Name | Company | Email | Confidence |
|------|------|---------|-------|------------|
| Developer | Rob Speyer | Tishman Speyer | rspeyer@tishmanspeyer.com | 95 — Verified |
| Architect | Dan Shannon | MdeAS Architects | dshannon@mdeas.com | 92 — Verified |
| General Contractor | Matthew Schimenti | Schimenti Construction | mschimenti@schimenti.com | 90 — Verified |
| Lender | — | Bank of America | — | 44 — Unconfirmed |
