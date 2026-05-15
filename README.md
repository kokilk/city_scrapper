# City Scrapper — Real Estate Intelligence Tool

Give it an address. Get back the company that owns the building, their top executives, and verified contact details (email, phone, LinkedIn).

---

## What It Does

**Input:** Any US property address

**Output:** Owner company → top 10–15 executives → verified emails, phones, LinkedIn profiles

**Example:**
```
Address: 432 Park Avenue, New York, NY
Owner:   CIM Group
People:  Shaul Kuba (Co-Founder) · Richard Ressler (Co-Founder) · ...
         with emails, phones, and LinkedIn URLs
```

---

## How the Pipeline Works

```
Address
  │
  ├─► Regrid          — Nationwide parcel ownership lookup (who owns the building)
  │   └─► NYC PLUTO / ACRIS — Free fallback for NYC addresses (auto, no key needed)
  │
  ├─► LLC Resolution  — If owner is a holding LLC, resolves to the real operating company
  │
  ├─► Company Validation — Confirms company from 2 independent web sources
  │
  ├─► Exa Web Search  — Finds company website + leadership pages
  │
  ├─► Claude (AI)     — Extracts names and titles from scraped content
  │
  ├─► Apollo.io       — Enriches each person: email + phone + LinkedIn (paid plan required)
  │   └─► Hunter.io   — Email fallback if Apollo doesn't return one
  │
  ├─► Person Validation — Verifies each person is real and at that company
  │
  └─► Email Validation  — Checks email deliverability
```

---

## APIs & Keys

Only two keys are required to get full results. The rest are fallbacks or optional.

| API | Purpose | Required? | Notes |
|-----|---------|-----------|-------|
| **Anthropic** | AI extraction + reasoning | ✅ Yes | Powers all Claude calls |
| **Regrid** | Nationwide parcel ownership | ✅ Yes | Primary property lookup |
| **Exa.ai** | Web search for company + leadership | ✅ Yes | Neural search |
| **Apollo.io** | Email + phone + LinkedIn enrichment | ⚠️ Paid plan | Needs Scale plan or API add-on for programmatic access |
| **Hunter.io** | Email discovery fallback | ✅ Active | Free tier: 50/mo |
| **Apify** | LinkedIn profile scraping | Optional | Fallback for LinkedIn |
| **Google Sheets** | Live output destination (batch mode) | Optional | Needs service account JSON |
| **NYC PLUTO/ACRIS** | Free NYC property data | Auto | No key — used automatically for NYC |

---

## Features

### Single Address Search
- Enter one address in the web UI
- Pipeline runs in ~30–60 seconds
- Returns owner company + leadership list with contacts

### Batch Upload (Excel)
- Upload an `.xlsx` file with up to 100+ addresses (one address per row)
- Processed in waves of 10 addresses in parallel
- **Live progress bar** updates in real time per address
- Each address shows status: `searching → found N` or `failed`
- Results pushed live to **Google Sheets** as each address completes
- One automatic retry per failed address before marking it as failed

### Validation
- **Company validation** — confirms owner from 2 independent sources, confidence scored High / Medium / Low
- **Person validation** — verifies each executive is real and currently at the company
- **Email validation** — checks deliverability before showing the email

---

## Project Structure

```
city_scrapper/
│
├── .env                    ← API keys (never commit this)
├── requirements.txt        ← Python dependencies
│
├── leadership/             ← Core pipeline
│   ├── pipeline.py         ← Main pipeline logic (all 4 steps)
│   ├── tools.py            ← All API integrations (Regrid, Apollo, Exa, Hunter, etc.)
│   ├── sheets.py           ← Google Sheets live push
│   ├── validation.py       ← Company, person, and email validation
│   ├── agent.py            ← Claude agent wrapper
│   └── prompts.py          ← LLM prompt templates
│
├── api/
│   └── server.py           ← FastAPI backend (port 8000)
│                             Endpoints: /run/leadership, /batch/upload, /batch/status/{id}
│
├── web/                    ← Next.js frontend (port 3000)
│   └── app/
│       └── page.tsx        ← Main UI (single search + batch upload tabs)
│
├── config/
│   ├── apis.py             ← Centralised API key loader
│   └── api_keys.env.example
│
└── output/                 ← Generated CSVs and JSONs (gitignored)
    └── leadership/
```

---

## Quick Start

```bash
# 1. Clone and set up
git clone https://github.com/kokilk/city_scrapper.git
cd city_scrapper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your API keys
cp config/api_keys.env.example .env
# Edit .env — minimum required: ANTHROPIC_API_KEY, REGRID_API_KEY, EXA_API_KEY

# 3. Start the backend
uvicorn api.server:app --reload --port 8000

# 4. Start the frontend (separate terminal)
cd web && npm install && npm run dev
# Open http://localhost:3000
```

---

## Environment Variables

```env
# ── AI (required) ──────────────────────────────
ANTHROPIC_API_KEY=

# ── Property Data ──────────────────────────────
REGRID_API_KEY=           # Nationwide parcel ownership (primary)
# NYC PLUTO + ACRIS: free, used automatically for NYC — no key needed

# ── Contact Enrichment ─────────────────────────
APOLLO_API_KEY=           # Needs Scale plan or API add-on for programmatic access
HUNTER_API_KEY=           # Email fallback (active on free tier)
APIFY_API_KEY=            # LinkedIn scraping (optional)

# ── Web Search ─────────────────────────────────
EXA_API_KEY=              # Required for leadership discovery
GOOGLE_CSE_API_KEY=       # Google search fallback (optional)
GOOGLE_CSE_ID=            # Google search fallback (optional)

# ── Google Sheets Output (batch mode) ──────────
GOOGLE_SHEET_ID=          # Sheet ID from the URL
GOOGLE_SERVICE_ACCOUNT_FILE=  # Path to service account JSON key

# ── Pipeline Settings ──────────────────────────
ENRICH_PHONE_ROLES=Developer,GC
```

---

## Google Sheets Setup (for Batch Mode)

1. Go to [Google Cloud Console](https://console.cloud.google.com) → IAM → Service Accounts → Create
2. Grant it **Editor** access to your Google Sheet
3. Download the JSON key file
4. Set `GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/key.json` in `.env`
5. Share your Google Sheet with the service account email address

If not configured, batch mode still works — results just won't push to Sheets.

---

## Apollo API Note

Apollo's `people/match` and `mixed_people/search` endpoints (used for contact enrichment) require a **Scale plan or API add-on** — the Professional plan includes UI credits but not programmatic API access. Contact Apollo support to enable API access on your account.

When Apollo is unavailable, the pipeline falls back to **Hunter.io** for emails and **Exa** for LinkedIn.

---

## Regrid Note

The Regrid trial token covers a limited number of counties. For full nationwide coverage, upgrade to a paid Regrid plan. For **NYC addresses**, the pipeline automatically uses the free **NYC PLUTO + ACRIS** dataset regardless of Regrid status.

---

## License

Private — not for public distribution.
