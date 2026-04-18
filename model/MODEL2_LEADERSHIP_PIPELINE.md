# Model 2 — Leadership Intelligence Pipeline

The fast, AI-powered pipeline. Given a building address, it finds the company that owns the building, then extracts the **top executives** at that company — with emails, phones, and LinkedIn profiles — in about 30 seconds.

---

## What It Finds

For each building, Model 2 identifies the **owner company** and then surfaces up to 15 of their senior leaders:

- CEO, President, COO, CFO
- Managing Directors, VPs, Partners
- Any named principals visible on the company's website or LinkedIn

**Example output for 28-07 Jackson Avenue (The JACX):**

| Rank | Name | Title | Company | Email | Confidence |
|------|------|-------|---------|-------|------------|
| 1 | Rob Speyer | CEO | Tishman Speyer | rspeyer@tishmanspeyer.com | High |
| 2 | Owen Thomas | President & COO | Tishman Speyer | — | Medium |

---

## How It Works (Step by Step)

```
Address Input
    │
    ▼
Step 1: Find Building Owner
    NYC PLUTO API (free) → owner LLC name
    If PLUTO fails → NYC DOB web scrape → permit applicant
    │
    ▼
Step 2: Resolve LLC → Real Company
    Claude Haiku reasons: "Is 'Waterbridge Court Square Holdings LLC'
    a shell for 'Waterbridge Capital'?"
    Exa neural search confirms
    │
    ▼
Step 3: Find Company Website
    Exa search: "{company name} official website"
    Filters out brokers, aggregators, building listing sites
    │
    ▼
Step 4: Extract Leadership
    Fetch company team/about page
    Claude Haiku extracts: name, title, company
    Returns ranked list (most senior first)
    │
    ▼
Step 5: Enrich Contacts (parallel)
    ├── Hunter.io → email by domain
    ├── Exa search → LinkedIn profile URL
    └── Apify → deep LinkedIn data (if key available)
    │
    ▼
Step 6: Save Output
    CSV + JSON per address
    Append to leadership_latest.csv (with --append flag)
```

---

## Output Format

**CSV columns (10):**

| Column | Description |
|--------|-------------|
| `rank` | Seniority rank (1 = most senior) |
| `full_name` | Person's full name |
| `title` | Job title |
| `company` | Company name |
| `email` | Email address (from Hunter.io) |
| `phone` | Phone number (if found) |
| `linkedin_url` | LinkedIn profile URL |
| `confidence` | High / Medium / Low |
| `property_address` | Source building address |
| `owner_entity` | Owner company name as found in PLUTO |

**Output files:**
- `output/leadership/{address}_{timestamp}.csv` — individual per-address file
- `output/leadership/{address}_{timestamp}.json` — full JSON with metadata
- `output/leadership/leadership_latest.csv` — combined append file (use `--append`)

---

## Confidence Labels

| Label | Meaning |
|-------|---------|
| **High** | Name + title confirmed from official company website |
| **Medium** | Found via LinkedIn or press mention, title plausible |
| **Low** | Single source, no corroboration |

---

## APIs Used

| API | What it provides | Notes |
|-----|-----------------|-------|
| **NYC PLUTO** | Building owner LLC lookup | Free, no key needed |
| **Exa.ai** | Neural web search — finds company websites, team pages, LinkedIn | Paid per search. Max 5 calls per address |
| **Anthropic Claude Haiku** | LLC resolution + leadership extraction from scraped HTML | Per token. Max 2 calls per address |
| **Hunter.io** | Email discovery by domain | Free: 50 searches/mo. Max 1 call per person |
| **Apify** | Deep LinkedIn profile scraping (title, headline, connections) | Per run. Optional — pipeline works without it |

### Cost Per Address (approximate)

| API | Calls | Approx Cost |
|-----|-------|-------------|
| Exa | 5 searches | ~$0.05 |
| Claude Haiku | 2 calls | ~$0.001 |
| Hunter | 1–15 calls | Free tier / ~$0.01 each paid |
| Apify | 0–1 runs | ~$0.10 per run |
| **Total** | | **~$0.05–$0.20 per address** |

---

## Running Model 2

### Single address
```bash
python3 leadership_fast.py "28-07 Jackson Avenue, Long Island City, NY"
```

### Append to combined file
```bash
python3 leadership_fast.py "30-30 47th Avenue, Long Island City, NY" --append
```

### Batch from CSV
```bash
python3 leadership_run.py --input addresses.csv --append
```

### Slash command (in Claude Code)
```
/leadership 28-07 Jackson Avenue, Long Island City, NY
```

---

## Required Environment Variables

```env
EXA_API_KEY=          ← exa.ai — neural search
ANTHROPIC_API_KEY=    ← anthropic.com — Claude Haiku
HUNTER_API_KEY=       ← hunter.io — email discovery
APIFY_API_KEY=        ← apify.com — LinkedIn scraping (optional)
```

---

## Speed

- **Single address:** 15–40 seconds
- **5-address batch:** 30–55 seconds (parallel enrichment)

Why it's fast:
- Uses Claude Haiku (fastest Claude model) not Sonnet/Opus
- Contact enrichment runs in parallel threads (`ThreadPoolExecutor`)
- Max 5 Exa calls + 2 Claude calls per address (hard limits)
- Fails fast — if PLUTO returns nothing, stops with `NOT FOUND` immediately

---

## Data Processed (April 2026)

Addresses run through Model 2:

| Neighborhood | Addresses | Output File |
|---|---|---|
| Long Island City | 5 | `25_01_Jackson_Avenue`, `30_30_47th_Avenue`, `28_07_Jackson_Avenue`, `28_11_Queens_Plaza_North`, `31_00_47th_Avenue` |
| Astoria | 3 | `34_12_36th_Street`, `21_21_44th_Drive`, `35_37_36th_Street` |
| Sunnyside | 4 | `48_02_48th_Avenue`, `48_43_32nd_Place`, `31_25_Thomson_Avenue`, `47_09_30th_Street` |
| Manhattan (test) | 1 | `350_5th_Ave` |

---

## NOT FOUND Cases

7 of 20 addresses returned `NOT FOUND`. Root causes:

| Cause | How common | Fix |
|-------|-----------|-----|
| Address not in PLUTO / DOB | ~30% | Add NYC ACRIS (free deed search) |
| Shell LLC / SPE with no public website | ~40% | Add OpenCorporates ($233/mo) |
| Company has no public leadership page | ~30% | Add Apollo.io ($49/mo) |

---

## Key Files

| File | Purpose |
|------|---------|
| [leadership/pipeline.py](../leadership/pipeline.py) | Core pipeline logic — all 6 steps |
| [leadership/tools.py](../leadership/tools.py) | `search_web()`, `fetch_webpage()`, `find_email()`, `find_linkedin_url()`, `apify_linkedin_scrape()` |
| [leadership/agent.py](../leadership/agent.py) | Claude Haiku agent wrapper |
| [leadership/prompts.py](../leadership/prompts.py) | LLM prompt templates for LLC resolution + leadership extraction |
| [leadership_fast.py](../leadership_fast.py) | CLI entry point |
| [leadership_run.py](../leadership_run.py) | Batch runner |

---

## Domain Filtering

The pipeline skips these categories when searching for the company's official website (to avoid returning a broker or listing site instead of the actual owner's website):

- **Brokers:** Cushman & Wakefield, CBRE, JLL, Colliers, Newmark, Savills
- **Listing sites:** LoopNet, CoStar, CommercialCafe, CREXi, PropertyShark, StreetEasy
- **Data aggregators:** RocketReach, Bloomberg, Crunchbase, ZoomInfo, D&B
- **News/reference:** NYTimes, WSJ, Bisnow, The Real Deal, Wikipedia, LinkedIn
- **Government/legal:** SEC.gov, SunBiz, dos.ny.gov
