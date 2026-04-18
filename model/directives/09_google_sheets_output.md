# Directive 09: Google Sheets Output

## Tab Naming

Each property run creates a tab named: `{AddressSlug}_{YYYY-MM-DD}`

- AddressSlug: address title-cased with non-alphanumeric chars stripped, max 30 chars
  Example: "123 Main St 90210" → "123MainSt90210"
- Date: ISO format of run date

Full example: `123MainSt90210_2026-04-08`

## Idempotency

If a tab with this name already exists:
- Clear data rows A2:Z (preserve header in row 1)
- Rewrite all rows from the latest run

This makes re-runs safe — no duplicate tabs, no stale data in old rows.

## Column Structure

| Column | Header | Source | Notes |
|--------|--------|--------|-------|
| A | Stakeholder ID | Generated UUID | Stable across re-runs of same property |
| B | Role | entity_extractor | Developer/Architect/GC/Subcontractor/Lender/Owner |
| C | Full Name | Primary source | Person or entity name |
| D | Company | Primary source | Empty if individual with no company |
| E | Phone | Shovels / Apollo | E.164: +15551234567 |
| F | Email | Shovels / Apollo / Hunter | Lowercase |
| G | LinkedIn URL | Shovels / Apollo | Full URL |
| H | Confidence Score | confidence_scorer | Integer 0–100 |
| I | Confidence Label | confidence_scorer | Verified / Probable / Unconfirmed |
| J | Independent Sources | cross_verifier | Count of independent data lineages |
| K | Source List | cross_verifier | Pipe-delimited: "Shovels|ATTOM|OpenCorporates" |
| L | Source Details | All stages | JSON: [{source, record_date, record_id}] |
| M | Permit Number | Shovels | Most recent relevant permit |
| N | Permit Date | Shovels | YYYY-MM-DD |
| O | Permit Type | Shovels TAGS | E.g. "electrical|plumbing" |
| P | Permit Value (USD) | Shovels | Numeric |
| Q | License Number | Shovels | Contractor license number |
| R | License Status | Shovels | Active / Expired / Suspended |
| S | License Expiry | Shovels | YYYY-MM-DD |
| T | Property Address | normalize_address | Standardized full address |
| U | County FIPS | normalize_address | 5-digit FIPS code |
| V | ATTOM Lender | ATTOM | Institutional lender name |
| W | ATTOM Loan Amount | ATTOM | USD numeric |
| X | Last Verified Date | pipeline_runner | Date this row was written |
| Y | Notes / Flags | cross_verifier | See flags below |
| Z | Raw Data Path | pipeline_runner | Path to .tmp/final_stakeholders.json |

## Flags (Column Y, pipe-delimited)

| Flag | Meaning |
|------|---------|
| SINGLE_SOURCE | Appears in only 1 independent source — treat with caution |
| LICENSE_EXPIRED | Contractor license is expired |
| LLC_UNRESOLVED | Entity is an LLC but no officers found in OpenCorporates |
| NO_PERMIT_DATA | Property has no permits in Shovels coverage |
| ARCHITECT_WEB_ONLY | Architect identified only via web search, not a permit |
| SUB_INFERRED | Subcontractor inferred from specialty permits, not named on main permit |
| ENRICHMENT_SKIPPED | Contact enrichment failed or was skipped due to API limits |

## Formatting Applied to New Tabs

- Row 1: Frozen (header always visible)
- Column H: Conditional formatting
  - Green (≥75): Verified stakeholders
  - Yellow (45–74): Probable stakeholders
  - Red (<45): Unconfirmed stakeholders
- All columns: Auto-filter enabled

## CCPA / Data Retention

Review and archive/delete rows older than 12 months.
Google Sheet rows with personal contact information (email, phone) are personal data
under CCPA and similar regulations. The pipeline does not auto-delete old rows —
this must be done manually or via a scheduled cleanup directive.

## Sharing the Output

The pipeline prints the Sheet URL on completion.
The Sheet is accessible to anyone with the service account's share permissions.
To share with your team: File → Share → Add people in the Google Sheet UI.
