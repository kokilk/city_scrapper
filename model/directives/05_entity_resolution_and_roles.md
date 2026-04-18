# Directive 05: Entity Resolution and Roles

## LLC Detection

When a name field contains legal entity suffixes, it's an entity (not a person).
Detect with this pattern: `LLC|LP|LLP|Inc|Corp|Trust|REIT|Holdings|Partners|Realty|Properties|Group`

When an entity is detected:
1. Record the entity name as `company` on the StakeholderCandidate
2. Trigger an OpenCorporates lookup for the entity name + state
3. If officers are found, create individual StakeholderCandidates for each current officer
4. If no officers found, flag the entity as `LLC_UNRESOLVED`

## Role Priority Order

When the same person/entity appears in multiple sources with conflicting roles,
use this priority order (first match wins):

1. Lender — ATTOM `lender_name` (definitive)
2. Architect — Shovels classification "architect" (definitive)
3. GC — Shovels classification "general" (definitive)
4. Subcontractor — Shovels classification specialty (definitive)
5. Developer — Permit applicant ≠ ATTOM deed owner (probable — flag SINGLE_SOURCE)
6. Owner — ATTOM deed owner or county assessor (authoritative)
7. Unknown — Officer on an LLC where role is ambiguous

## Officer Role Mapping

From OpenCorporates officer `position` field:

| Position contains | Assigned Role |
|------------------|---------------|
| "manager", "member", "managing" | Developer |
| "president", "ceo", "principal" | Developer |
| "director" | Owner |
| "agent", "registered agent" | Unknown (skip unless no other contacts found) |
| "secretary", "treasurer" | Unknown |
| Empty | Owner |

Skip officers with a non-null `end_date` (former officers).

## Cross-Source Ownership Discrepancy

If ATTOM shows owner = "ACME HOLDINGS LLC" but the permit shows owner = "JOHN SMITH":
- Both records are kept as separate StakeholderCandidates
- ACME HOLDINGS LLC → role=Owner, flag → triggers OpenCorporates lookup
- JOHN SMITH → role=Developer (probable — he filed the permit)
- These two often resolve to the same person via OpenCorporates officer lookup

## Name Normalization Rules

For matching purposes only (original names are preserved in output):
1. Lowercase entire string
2. Strip entity suffixes (LLC, Inc, Corp, etc.)
3. Strip punctuation except spaces
4. Compare normalized strings

Example: "SMITH CAPITAL GROUP LLC" → "smith capital group"
         "Smith Capital Group, Inc." → "smith capital group"
These would be fuzzy-matched as the same entity.
