# City Scrapper — System Architecture

Read this file to fully understand the system. You do not need to read any other file to get oriented.

---

## What This System Does

Takes a US property address → finds who owns the building → finds that company's top executives → returns verified contact info (email, phone, LinkedIn) for each person.

**Single address:** ~30–60 seconds end-to-end
**Batch (100 addresses):** runs 10 in parallel per wave, streams live progress to the UI

---

## Stack

| Layer | Technology | Port |
|---|---|---|
| Frontend | Next.js (TypeScript, Tailwind) | 3000 |
| Backend | FastAPI (Python) | 8000 |
| AI | Anthropic Claude (claude-sonnet via API) | — |

---

## File Map

```
city_scrapper/
│
├── api/server.py           ← FastAPI app — all HTTP endpoints
│
├── leadership/
│   ├── pipeline.py         ← THE core pipeline (run_pipeline function)
│   ├── tools.py            ← All external API calls (Regrid, Apollo, Exa, Hunter, etc.)
│   ├── validation.py       ← Company / person / email validation
│   ├── sheets.py           ← Google Sheets live push (batch mode)
│   ├── agent.py            ← Claude agent wrapper (used in pipeline)
│   └── prompts.py          ← LLM prompt strings
│
├── web/app/page.tsx        ← Entire frontend UI (single file, React)
│
├── config/
│   ├── apis.py             ← Centralised env var loader
│   └── api_keys.env.example
│
├── .env                    ← All API keys live here
├── requirements.txt        ← Python deps
└── railway.json            ← Railway deployment config (backend)
```

Everything important lives in three files: `api/server.py`, `leadership/pipeline.py`, `leadership/tools.py`.

---

## Pipeline Steps (leadership/pipeline.py → run_pipeline)

```
run_pipeline(address, city, state, zip_code)
│
├── STEP 1 — find_building_owner()
│   ├── regrid_lookup()          tools.py  Nationwide parcel ownership via Regrid API
│   ├── _pluto_lookup()          pipeline  NYC PLUTO open data (free, auto for NYC)
│   ├── acris_owner_by_address() tools.py  NYC ACRIS deed records (free, auto for NYC)
│   ├── _dob_lookup()            pipeline  NYC DOB permit records (free, auto for NYC)
│   └── _web_owner_lookup()      pipeline  Exa web search fallback
│
│   Then: _resolve_llc_to_company()
│         If the owner is a holding LLC (e.g. "28-07 Jackson LLC"),
│         resolves it to the real operating company via web search + Claude
│
├── CHECKPOINT 1 — validate_company()          validation.py
│   Confirms the company from 2 independent web sources
│   Returns: confidence = High / Medium / Low
│
├── STEP 2 — find_company_website()
│   Exa search for company homepage. Validates domain name overlaps company name.
│
├── STEP 3 — Gather leadership data (parallel)
│   ├── apollo_search_by_org()   tools.py  Pull top 15 execs from Apollo by company name
│   ├── scrape_team_page()       pipeline  Scrape /about, /team, /leadership pages
│   └── 5x search_web()          tools.py  Exa queries for CEO, VP, directors, LinkedIn
│
├── STEP 4 — extract_leaders()
│   Single Claude call: given all scraped text, extract list of {name, title}
│   Apollo org results merged in: anyone not found by Claude is added
│
└── STEP 5 — Parallel enrichment (_enrich_one per person, max 6 workers)
    ├── enrich_with_apollo()     tools.py  Email + phone + LinkedIn (X-Api-Key header)
    ├── find_linkedin_url()      tools.py  Exa search for LinkedIn profile (fallback)
    └── find_email()             tools.py  Hunter.io email lookup (fallback)
    │
    ├── CHECKPOINT 2 — validate_people_batch()   validation.py
    │   Verifies each person is real and at this company via web search
    │
    └── CHECKPOINT 3 — validate_emails_batch()   validation.py
        MX record check + optional NeverBounce / ZeroBounce verification
```

**Return value:** `list[dict]` — one dict per person with these keys:
```
rank, full_name, title, company, email, phone, linkedin_url, confidence,
property_address, owner_entity, data_source,
person_verified, person_sources, person_validation_note,
email_valid, email_deliverable, email_check_note,
company_confidence, company_validation_note
```

---

## API Endpoints (api/server.py)

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Serves legacy HTML UI (dark theme, embedded) |
| GET | `/health` | Returns `{"status": "ok"}` |
| POST | `/run/leadership` | Single address search — streams SSE log lines then returns JSON |
| POST | `/run/model1` | Placeholder (returns not implemented) |
| GET | `/download/leadership` | Download a CSV from the output folder |
| POST | `/search` | Single address search — requires `{address, city, state}` separately |
| POST | `/batch/upload` | Upload `.xlsx` file → starts batch → returns `{batch_id, total}` |
| GET | `/batch/status/{batch_id}` | SSE stream of batch progress |

### Batch Flow (server.py)

```
POST /batch/upload
  → _parse_excel()           reads first column, skips header row
  → creates _batches[batch_id] = {addresses, items[], completed, done}
  → threading.Thread(_run_batch) starts in background
  → returns {batch_id, total}

_run_batch(batch_id)
  → loops in waves of 10 (BATCH_SIZE = 10)
  → ThreadPoolExecutor(10 workers) runs _process_one() per address
  → each _process_one():
      1. calls run_pipeline()
      2. on exception: sets status="retrying", tries once more
      3. on second failure: status="failed"
      4. on success: status="done", stores leaders count
      5. calls append_results() → pushes row to Google Sheets

GET /batch/status/{batch_id}
  → SSE stream, polls _batches[batch_id] every 1.5s
  → yields event: progress with {completed, total, items, done, sheet_id}
  → closes stream when state["done"] == True
```

### In-Memory Batch State

```python
_batches[batch_id] = {
    "addresses": ["123 Main St, NY", ...],
    "items": [
        {"address": "...", "status": "pending|searching|done|retrying|failed", "count": 0},
        ...
    ],
    "completed": 0,
    "done": False,
    "sheet_id": "google_sheet_id_or_empty"
}
```

---

## Frontend (web/app/page.tsx)

Single React component file. Two tabs:

### Tab 1 — Single Address
- User types full address (e.g. `432 Park Avenue, New York, NY 10022`)
- On submit: POST to `/run/leadership` via SSE (`EventSource`)
- Streams log lines live while pipeline runs
- On completion: renders a results table (name, title, email, phone, LinkedIn, confidence badge)
- Download CSV button

### Tab 2 — Batch Upload
- Drag-and-drop or click to upload `.xlsx`
- On upload: POST to `/batch/upload`
- Opens `EventSource` to `/batch/status/{batchId}`
- Shows overall progress bar (`completed / total`)
- Shows per-address row with status badge: `pending → searching → found N / failed`
- Google Sheets link appears once results start flowing (if Sheets is configured)
- Stats row: done / retried / failed counts

**API base URL:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
```
Set `NEXT_PUBLIC_API_URL` in production to the Railway backend URL.

---

## Tools (leadership/tools.py)

Every external API call lives here. Nothing else imports requests directly.

| Function | API | Auth | Notes |
|---|---|---|---|
| `regrid_lookup` | Regrid | Bearer token | Nationwide parcel lookup |
| `acris_owner_by_address` | NYC ACRIS | None (free) | NYC deed records |
| `acris_current_owner` | NYC ACRIS | None (free) | By block/lot |
| `search_web` | Exa → Google CSE → DDG | X-Api-Key | Tries Exa first, falls back |
| `fetch_webpage` | HTTP | None | Raw HTML fetcher |
| `enrich_with_apollo` | Apollo | X-Api-Key header | Per-person enrichment |
| `apollo_search_by_org` | Apollo | X-Api-Key header | Org-level people search |
| `find_linkedin_url` | Exa | X-Api-Key | Finds + validates LinkedIn URL |
| `apify_linkedin_scrape` | Apify | Bearer | Scrapes LinkedIn profiles |
| `find_email` | Hunter.io | api_key param | Email discovery by domain |

**Apollo auth note:** Key goes in `X-Api-Key` header (NOT in JSON body). Body-based auth was deprecated by Apollo. `mixed_people/search` and `people/match` require Scale plan or API add-on — Professional plan only covers UI credits.

---

## Validation (leadership/validation.py)

### validate_company(company, address, city, state)
- Runs 2 independent Exa web searches for the company
- Returns `{confidence, sources_found, validation_note}`
- Confidence: `High` (2/2), `Medium` (1/2), `Low` (0/2)

### validate_person(name, company)
- Web search to confirm person works at the company
- Returns `{verified: bool, sources: int, note: str}`

### validate_people_batch(people, company)
- Runs validate_person in parallel (6 workers) for up to 15 people

### validate_email(email)
- MX record check first (DNS)
- Optional: NeverBounce or ZeroBounce API if keys are set
- Returns `{valid, deliverable, note}`

### validate_emails_batch(people)
- Runs validate_email in parallel for all people with emails

---

## Google Sheets (leadership/sheets.py)

- Uses `gspread` + Google service account JSON
- Silent no-op if `GOOGLE_SERVICE_ACCOUNT_FILE` is not set (batch still works)
- `append_results(address, leaders, batch_id, status)` — writes one row per person
- Headers: `Address, Company, Owner Entity, Source, Company Confidence, Name, Title, Email, Phone, LinkedIn, Verified, Email Valid, Data Source, Status, Batch ID`
- Thread-safe via `threading.Lock()`
- `sheets_configured()` → returns True only if credentials file exists

---

## Environment Variables (.env)

```env
# Required
ANTHROPIC_API_KEY=        # Claude API
REGRID_API_KEY=           # Parcel ownership
EXA_API_KEY=              # Web search (primary)

# Contact enrichment
APOLLO_API_KEY=           # Scale plan needed for API access
HUNTER_API_KEY=           # Email fallback
APIFY_API_KEY=            # LinkedIn scraping

# Web search fallbacks
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=

# Email validation (optional)
NEVERBOUNCE_API_KEY=
ZEROBOUNCE_API_KEY=

# Google Sheets (batch output)
GOOGLE_SHEET_ID=
GOOGLE_SERVICE_ACCOUNT_FILE=

# Pipeline
ENRICH_PHONE_ROLES=Developer,GC
```

---

## Key Design Decisions

1. **Regrid first, NYC open data automatic** — Regrid handles nationwide. For any NYC address, PLUTO + ACRIS are tried automatically as free alternatives regardless of Regrid result.

2. **LLC resolution** — Many NYC buildings are owned by holding LLCs. `_resolve_llc_to_company` detects LLC-style names and uses Exa + Claude to find the real operating company behind it.

3. **Single Claude extraction call** — All scraped text (website + 5 Exa queries) is combined into one prompt. Claude extracts names + titles in a single call. This keeps latency down and cost predictable.

4. **Apollo org search + Claude merge** — `apollo_search_by_org` runs in parallel with Exa queries. Claude-extracted names are the base; Apollo names not found by Claude are appended. Deduped by lowercased name.

5. **Prefetched Apollo data** — People sourced directly from Apollo org search carry their contact data (`_apollo_prefetched`). `_enrich_one` skips the per-person Apollo call for these, saving credits.

6. **Batch waves** — 100 addresses processed as waves of 10 in parallel. Not all 100 at once — avoids rate limit blowouts on Regrid and Apollo.

7. **Retry once** — Each address gets one automatic retry on any exception before being marked `failed`.

8. **SSE for live progress** — Backend streams `text/event-stream` responses. Frontend uses `EventSource` (native browser API). No WebSockets needed.

9. **Validation is additive** — Company and person validation add confidence scores but don't block results. A low-confidence result still shows up — the user decides what to do with it.

---

## Running Locally

```bash
# Backend
uvicorn api.server:app --reload --port 8000

# Frontend
cd web && npm run dev

# UI
open http://localhost:3000
```

---

## Known Limitations

- **Apollo API** — requires Scale plan for `people/match` and `mixed_people/search`. Professional plan only has UI credits. Pipeline falls back to Hunter + Exa when Apollo is blocked.
- **Regrid trial** — covers limited counties. NYC always works via PLUTO/ACRIS regardless.
- **In-memory batch state** — `_batches` dict is lost on server restart. Batch jobs don't survive restarts.
- **Google Sheets** — requires manual service account setup. Not configured by default.
- **Shell LLCs with no public presence** — if owner is a blank-shell LLC with zero web footprint, pipeline returns a placeholder with company info but no leaders.
