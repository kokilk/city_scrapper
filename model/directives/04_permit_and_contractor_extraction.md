# Directive 04: Permit and Contractor Extraction

## Primary Source: Shovels.ai

Shovels is the primary source for permit-level stakeholder discovery.
It covers 85%+ of US population, 1,800+ jurisdictions, 150M+ permits.

## What to Fetch

1. **Permits**: `GET /v2/permits?address={address}&status=final,active,in_review`
   - Paginate in pages of 50 until exhausted or 200 permits reached
   - Filter: `status=final,active,in_review` (exclude denied/voided)
   - On properties with many permits (apartment complex, large commercial): cap at 200,
     take the 200 most recent by `issue_date`

2. **Contractor profiles**: `GET /v2/contractors/{contractor_id}`
   - Fetch for every unique `contractor_id` found in permits
   - Run all concurrently with `asyncio.Semaphore(10)`

## Role Classification from CLASSIFICATION_DERIVED

The `classification_derived` field on contractor profiles maps to roles:

| classification_derived contains | Assigned Role |
|---------------------------------|---------------|
| "architect", "architecture", "design" | Architect |
| "general", "contractor of record", "builder" | GC |
| "electrical", "plumbing", "hvac", "mechanical" | Subcontractor |
| "roofing", "framing", "concrete", "masonry" | Subcontractor |
| "glazing", "curtain wall", "drywall", "insulation" | Subcontractor |
| "solar", "pv", "fire", "sprinkler" | Subcontractor |
| Any other or empty | GC (default) |

## Permit Applicant vs. Owner

- `applicant_name` on the permit is the party who FILED for the permit
  → Often the developer, GC, or their agent
- `owner_name` on the permit is self-reported by the applicant
  → Compare to ATTOM `owner1LastName` to detect developer vs. owner discrepancies
- If `applicant_name` ≠ ATTOM owner → classify applicant as "Developer" (flagged as
  single-source unless corroborated by OpenCorporates)

## No Permit Data Edge Case

If Shovels returns zero permits:
1. Check `.tmp/shovels_permits.json` — is it an empty array `[]` or an error?
2. If empty array: property has no permit history in Shovels' coverage
3. Flag all remaining stakeholders as `NO_PERMIT_DATA`
4. Pipeline continues with ATTOM + county assessor only
5. All results will be Unconfirmed (no cross-verification possible without permit data)

## Architect Gap

Architects rarely appear in structured permit fields.
They appear in PDF plan sets attached to permits (not extracted by Shovels).

Fallback: After pipeline completes, if no Architect role was found, the agent should
run an Exa web search: `"{full_address}" architect of record`
- Results flagged `ARCHITECT_WEB_ONLY` and confidence label forced to "Unconfirmed"
- Never promote web-search-only architect to Verified without a second source

## Subcontractor Gap

Building permits list the GC, not subcontractors.
Shovels infers specialty sub-permits by `CLASSIFICATION_DERIVED` on separate permits
pulled at the same address in the same time window.
All inferred subcontractors are flagged `SUB_INFERRED` and capped at "Probable".
