# Directive 06: Contact Enrichment

## Enrichment Strategy

For each StakeholderCandidate, attempt in this order:
1. **Check existing data**: If Shovels already returned both email AND phone for this
   stakeholder → skip enrichment entirely (saves API credits)
2. **Apollo**: `POST /v1/people/match` with name + company → email, phone, LinkedIn
3. **Hunter fallback**: If Apollo returns no email → `GET /v2/domain-search` with
   company domain → email list

## Apollo Configuration

**Endpoint**: `POST https://api.apollo.io/v1/people/match`

**Payload**:
```json
{
  "name": "First Last",
  "organization_name": "Company Name",
  "reveal_personal_emails": true,
  "reveal_phone_number": true  // only for ENRICH_PHONE_ROLES
}
```

**Phone enrichment policy** (IMPORTANT — costs 5 credits each):
- Only reveal phone for roles in `ENRICH_PHONE_ROLES` env var (default: Developer, GC)
- Never reveal phone for: Owner, Lender, Architect, Subcontractor, Unknown
- This conserves credits: at $59/mo Basic (10,000 credits), allows 100+ properties/month

## Hunter Configuration

**Endpoint**: `GET https://api.hunter.io/v2/domain-search?domain={domain}&api_key={key}`

**Domain extraction**: Parse company name or website for domain:
- "Acme Construction LLC" → try Google to find domain (or skip Hunter)
- "acmeconstruction.com" → domain = "acmeconstruction.com"
- If no domain can be inferred → skip Hunter

**Email selection priority**:
1. Personal email matching person's first/last name
2. First personal-type email in results
3. Do not use generic emails (info@, contact@, hello@)

## Rate Limits

- Apollo: `asyncio.Semaphore(3)` — max 3 concurrent requests
- Hunter: `asyncio.Semaphore(5)` — max 5 concurrent requests

## Credit Tracking

Apollo credit usage is not tracked locally (the API handles it).
If Apollo returns HTTP 402 (payment required) or 429 (rate limited):
- Log the error
- Skip enrichment for remaining candidates
- Do NOT crash the pipeline
- Flag affected stakeholders with `ENRICHMENT_SKIPPED`

## What to Do When All Enrichment Fails

If both Apollo and Hunter are unavailable (no keys, rate limits):
- Pipeline continues with contact fields empty
- All stakeholders will have lower confidence scores (missing contact bonus)
- Recommend user to manually verify contact info for Verified/Probable rows
