# City Scraper — NYC Real Estate Intelligence

A two-model intelligence system that takes a building address and automatically finds every key person connected to that property — owners, executives, developers, architects, contractors, lenders — along with verified contact details.

---

## What This Does

You give it an address. It gives you people and contacts.

**Input:** `28-07 Jackson Avenue, Long Island City, NY`

**Output:** Rob Speyer (CEO, Tishman Speyer) · Dan Shannon (Managing Partner, MdeAS Architects) · Matthew Schimenti (President, Schimenti Construction) · Bank of America (Lender, $425M) — all with emails, phones, LinkedIn

---

## Two Models

This project has two distinct pipelines built for different use cases:

| | Model 1 — Stakeholder Pipeline | Model 2 — Leadership Pipeline |
|---|---|---|
| **What it finds** | All roles: Owner, Developer, Architect, GC, Lender, Leasing Agent | Top executives at the building's owner company |
| **Depth** | Deep — multiple sources cross-verified | Fast — single-pass agent |
| **Speed** | 2–5 minutes per address | 15–40 seconds per address |
| **Output** | CSV + Google Sheet (15 columns) | CSV + JSON (10 columns) |
| **Entry point** | `python3 execution/pipeline_runner.py` | `python3 leadership_fast.py` |
| **Confidence scoring** | Yes (0–100 with labels) | Yes (High / Medium / Low) |

Full details: [Model 1 docs](model/MODEL1_STAKEHOLDER_PIPELINE.md) · [Model 2 docs](model/MODEL2_LEADERSHIP_PIPELINE.md)

---

## Project Structure

```
city_scraper/
│
├── README.md                        ← You are here
├── .env.example                     ← API key template (copy to .env)
├── requirements.txt                 ← Python dependencies
│
├── model/                           ← All documentation
│   ├── MODEL1_STAKEHOLDER_PIPELINE.md   ← Deep dive on Model 1
│   ├── MODEL2_LEADERSHIP_PIPELINE.md    ← Deep dive on Model 2
│   ├── PLAN.md                          ← Original design plan
│   └── directives/                      ← 11 SOPs for Model 1 stages
│       ├── 01_stakeholder_pipeline_overview.md
│       ├── 02_address_normalization.md
│       ├── 03_data_sources_and_api_keys.md
│       └── ... (11 total)
│
├── execution/                       ← Model 1: Full stakeholder pipeline
│   ├── pipeline_runner.py           ← Entry point — run this
│   ├── models.py                    ← Shared dataclasses
│   ├── api_client.py                ← Async HTTP with retry + rate limiting
│   ├── normalize_address.py         ← Smarty address verification
│   ├── pluto_lookup.py              ← NYC PLUTO owner lookup (free)
│   ├── permit_scraper.py            ← NYC DOB permit scraping (free)
│   ├── shovels_permit_fetch.py      ← Shovels permit data
│   ├── shovels_contractor_fetch.py  ← Shovels contractor profiles
│   ├── attom_property_fetch.py      ← ATTOM owner + lender data
│   ├── opencorporates_entity_lookup.py ← LLC → human officer resolution
│   ├── county_assessor_router.py    ← County FIPS routing
│   ├── county_assessor_fetch.py     ← County assessor records
│   ├── entity_extractor.py          ← Role classification
│   ├── contact_enricher.py          ← Apollo + Hunter enrichment
│   ├── cross_verifier.py            ← Multi-source verification
│   ├── confidence_scorer.py         ← 0–100 scoring engine
│   ├── deduplicator.py              ← Merge duplicate records
│   └── sheets_writer.py             ← Google Sheets output
│
├── leadership/                      ← Model 2: Fast leadership pipeline
│   ├── pipeline.py                  ← Core pipeline logic
│   ├── tools.py                     ← search_web, fetch_webpage, find_email, find_linkedin_url
│   ├── agent.py                     ← Claude Haiku agent wrapper
│   ├── prompts.py                   ← LLM prompt templates
│   └── __init__.py
│
├── agent/                           ← Original prototype agent (v0)
│   ├── agent.py                     ← Claude Sonnet agentic loop
│   ├── tools.py                     ← Early tool set
│   └── prompts.py
│
├── api/                             ← REST API server (Railway)
│   ├── server.py
│   ├── requirements.txt
│   ├── Procfile
│   └── railway.json
│
├── web/                             ← Next.js web frontend
│   ├── app/
│   ├── components/
│   └── ...
│
├── leadership_fast.py               ← Model 2 CLI entry point
├── leadership_run.py                ← Model 2 batch runner
├── batch_run.py                     ← Multi-address batch processor
├── run.py                           ← Prototype agent CLI entry point
│
├── input/                           ← Address lists to process
│   ├── addresses.csv
│   ├── addresses_astoria.csv
│   └── addresses_remaining.csv
│
└── output/                          ← All output (gitignored)
    ├── LIC_all_stakeholders_FINAL.csv
    └── leadership/                  ← Per-address CSV + JSON
```

---

## APIs Used

### Model 1 — Stakeholder Pipeline

| API | Purpose | Cost |
|-----|---------|------|
| **Smarty Streets** | Address normalization + validation | Free: 250/mo |
| **NYC PLUTO** | Building owner lookup from city database | Free (no key) |
| **NYC DOB** | Permit history and contractor records | Free (no key) |
| **Shovels.ai** | Primary permit + contractor data source | Paid: $599/mo |
| **ATTOM Data** | Property ownership + lender + deed records | Paid: ~$95/mo |
| **OpenCorporates** | Resolve LLCs → named human officers | Free: 200/mo |
| **Apollo.io** | Email + phone + LinkedIn enrichment | Free: 100 credits/mo |
| **Hunter.io** | Email discovery fallback | Free: 50 searches/mo |
| **Google Sheets API** | Output destination | Free |

### Model 2 — Leadership Pipeline

| API | Purpose | Cost |
|-----|---------|------|
| **NYC PLUTO** | Building owner lookup | Free (no key) |
| **Exa.ai** | Neural web search (find company + team pages) | Paid per search |
| **Anthropic Claude Haiku** | Extract + reason over scraped data | Per token |
| **Hunter.io** | Email discovery | Free: 50 searches/mo |
| **Apify** | Deep LinkedIn profile scraping | Per run |

---

## Quick Start

### Model 2 — Leadership Pipeline (recommended for getting started)

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/city_scrapper
cd city_scrapper
pip install -r requirements.txt

# 2. Add keys to .env
cp .env.example .env
# Fill in: EXA_API_KEY, ANTHROPIC_API_KEY, HUNTER_API_KEY

# 3. Run a single address
python3 leadership_fast.py "28-07 Jackson Avenue, Long Island City, NY"

# 4. Append more addresses to the same output file
python3 leadership_fast.py "30-30 47th Avenue, Long Island City, NY" --append
```

Output saved to `output/leadership/leadership_latest.csv`

### Model 1 — Full Stakeholder Pipeline

```bash
# Requires more API keys — see docs/MODEL1_STAKEHOLDER_PIPELINE.md
python3 execution/pipeline_runner.py --address "350 5th Ave" --zip "10118"
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Model 2 — required
EXA_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
HUNTER_API_KEY=your_key_here

# Model 1 — required for full stakeholder pipeline
SMARTY_AUTH_ID=your_key_here
SMARTY_AUTH_TOKEN=your_key_here
SHOVELS_API_KEY=your_key_here
ATTOM_API_KEY=your_key_here
OPENCORPORATES_API_KEY=your_key_here
APOLLO_API_KEY=your_key_here
GOOGLE_SHEET_ID=your_sheet_id_here

# Optional
APIFY_API_KEY=your_key_here
ENRICH_PHONE_ROLES=Developer,GC
```

---

## Data Processed

As of April 2026, the pipeline has processed **20 addresses** across 4 Queens neighborhoods:

| Neighborhood | Addresses |
|---|---|
| Long Island City | 5 |
| Astoria | 3 |
| Sunnyside | 4 |
| Woodside | 4 |
| Other (Manhattan test) | 4 |

Combined output: **81 stakeholders** identified across all addresses.

---

## Known Limitations

- **Shell LLCs** with no public leadership (7 of 20 addresses returned NOT FOUND)
- **NYC DOB permit API** times out occasionally — manual lookup fallback documented
- **Hunter.io** monthly credit limit can exhaust on large batches (pipeline continues without email)
- **LinkedIn URLs** are flagged `VERIFY_LINKEDIN` as some profiles are approximate matches

### Phase 2 Planned Improvements
- Add NYC ACRIS (free deed/mortgage filings) to catch shell LLCs
- Add OpenCorporates to Model 2 for LLC officer resolution
- Add Apollo.io to Model 2 for higher email hit rate

---

## License

Private — not for public distribution.
