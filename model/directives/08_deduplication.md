# Directive 08: Deduplication

## Why Deduplication is Critical

The same person may appear as:
- The LLC officer (OpenCorporates) AND the permit applicant (Shovels)
- The ATTOM owner AND the county assessor owner
- The same contractor under different entity names on different permits

Without deduplication, the sheet would have duplicate rows, inflating apparent stakeholder count.

## Merge Trigger Conditions (in priority order)

1. **Phone exact match** (E.164 normalized: `+15551234567`)
   - If two stakeholders share the same normalized phone → merge
2. **Email exact match** (lowercased)
   - If two stakeholders share the same email → merge
3. **LinkedIn URL exact match** (trailing slash stripped)
   - If two stakeholders share the same LinkedIn URL → merge
4. **Name fuzzy match + same company**
   - `rapidfuzz.token_sort_ratio(normalized_name_a, normalized_name_b) > 88`
   - AND both have the same company name (or one has no company)
   - → merge

## DO NOT Merge Conditions

- Same name, different non-empty companies → keep separate
  (e.g., "John Smith" at "Acme LLC" vs. "John Smith" at "Smith Realty Inc" are different people)
- Same company name, completely different people → keep separate
  (e.g., two officers of the same LLC are different rows)

## Name Normalization (for matching only — original preserved in output)

1. Lowercase
2. Strip entity suffixes: LLC, LP, Inc, Corp, Trust, etc.
3. Remove punctuation except spaces
4. Strip leading/trailing whitespace

Example: "SMITH CAPITAL GROUP LLC" → "smith capital group"
         "Smith Capital Group, Inc." → "smith capital group"

## Merge Rules (what the winner keeps)

| Field | Rule |
|-------|------|
| raw_name / company | From the highest source_authority record |
| source_records | Union of all records (deduped by record_id) |
| confidence_score | Maximum of all merged records |
| flags | Union of all flags |
| email | Winner's email, or loser's if winner is empty |
| phone | Winner's phone, or loser's if winner is empty |
| linkedin_url | Winner's, or loser's if winner is empty |
| stakeholder_id | New UUID assigned at merge time |

**Source authority** (for determining winner):
Sum of `SOURCE_WEIGHTS` for all source_records.
Shovels+ATTOM > OpenCorporates > Apollo+Hunter.

## After Merging: Recalculate

After merging source_records, recalculate:
- `independent_source_count` (may increase)
- `confidence_score` (may increase due to more sources)
- `confidence_label` (may upgrade from Probable → Verified)

The deduplicator script handles this automatically.
