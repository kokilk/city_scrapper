# Directive 03: Data Sources and API Keys

## Required Environment Variables

Set all of these in `.env` before running the pipeline.

| Variable | Service | Where to Get | Free Tier | Notes |
|----------|---------|-------------|-----------|-------|
| `SMARTY_AUTH_ID` | Smarty US Street | smarty.com | 250 lookups/mo | Required first |
| `SMARTY_AUTH_TOKEN` | Smarty US Street | smarty.com | 250 lookups/mo | Pair with AUTH_ID |
| `SHOVELS_API_KEY` | Shovels.ai | shovels.ai | None (paid: $599/mo) | Primary stakeholder source |
| `ATTOM_API_KEY` | ATTOM Data | api.attomdata.com | None (paid: ~$95/mo) | Owner + lender |
| `OPENCORPORATES_API_KEY` | OpenCorporates | opencorporates.com/info/api | 200 req/mo | Optional, improves LLC resolution |
| `APOLLO_API_KEY` | Apollo.io | apollo.io | 100 credits/mo | Contact enrichment |
| `HUNTER_API_KEY` | Hunter.io | hunter.io | 50 searches/mo | Email fallback |
| `GOOGLE_SHEET_ID` | Google Sheets | See below | Free | Output destination |
| `ENRICH_PHONE_ROLES` | Pipeline config | Set in .env | N/A | Default: "Developer,GC" |

## What Each Source Returns

### Shovels.ai (PRIMARY — most valuable)
Fields from permit records: `permit_id`, `file_date`, `issue_date`, `job_value`,
`status`, `tags` (permit type), `applicant_name`, `applicant_email`, `applicant_phone`,
`owner_name`, `owner_email`, `owner_phone`, `contractor_id`

Fields from contractor profiles: `biz_name`, `classification_derived`, `primary_email`,
`primary_phone`, `website`, `linkedin_url`, `license`, `license_exp_date`,
`status_detailed`, `permit_count`, `avg_job_value`

### ATTOM Data Solutions
Fields: `owner1LastName`, `owner1FirstName`, `corporateName`, `mailingAddressOneLine`,
`lenderName`, `amount1stMtge`, `loanType1stMtge`, `loanTermMonths1stMtge`,
`salesDate`, `salesAmt`, `deedType`

### OpenCorporates
Fields: `company_name`, `company_number`, `jurisdiction_code`, `company_type`,
`incorporation_date`, `current_status`, `registered_agent_name`, `officers[]`
Officer fields: `name`, `position`, `start_date`, `end_date`, `address`

### Apollo.io
Endpoint: `POST /v1/people/match`
Fields: `email`, `phone_numbers[]`, `linkedin_url`, `title`, `seniority`, `department`
Cost: 1 credit per email reveal, 5 credits per phone reveal

### Hunter.io
Endpoint: `GET /v2/domain-search`
Fields: `emails[].value`, `emails[].confidence`, `emails[].type`, `emails[].first_name`,
`emails[].last_name`, `emails[].position`
Cost: 1 credit per domain search

## Source Independence Matrix

These pairs are NOT independent (same data lineage — don't double-count):
- ATTOM + County Assessor = both from recorded deed/tax records
- Apollo + Hunter = both commercial contact databases

These pairs ARE independent:
- Shovels + ATTOM (permit database vs. deed record)
- Shovels + OpenCorporates (permit vs. SOS filing)
- ATTOM + OpenCorporates (deed vs. SOS filing)
- Any government source + Apollo/Hunter

## Missing Key Behavior

If a key is missing, the pipeline:
- Skips that source entirely
- Writes `{"_status": "SKIPPED", "_reason": "No API key"}` to the .tmp file
- Continues to the next stage without crashing
- Records the skip in `run_summary.json` source_statuses

## Google Sheets Setup

1. Go to console.cloud.google.com → Create or select a project
2. Enable "Google Sheets API" and "Google Drive API"
3. IAM & Admin → Service Accounts → Create Service Account
4. Create a JSON key → download as `credentials.json` → place in project root
5. Create a Google Sheet → copy the ID from the URL:
   `https://docs.google.com/spreadsheets/d/{THIS_IS_THE_ID}/edit`
6. Share the sheet with the service account email (format: `name@project.iam.gserviceaccount.com`)
7. Set `GOOGLE_SHEET_ID=` in `.env`

## Rate Limit Summary

| Source | Rate Limit | Pipeline Strategy |
|--------|-----------|-------------------|
| Smarty | 1000/day (free) | 1 call per run |
| Shovels | Per plan | Semaphore(10), backoff on 429 |
| ATTOM | Per plan | Semaphore(5), backoff on 429 |
| OpenCorporates | 50/day (free) | Hard limit: 45/day with buffer |
| Apollo | Per credits | Semaphore(3), phone only for Developer+GC |
| Hunter | Per credits | Semaphore(5) |
| Google Sheets | 300 req/min | batch_update() in one call |
