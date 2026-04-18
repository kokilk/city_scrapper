# Directive 07: Confidence Scoring

## Formula

```
confidence_score = min(source_score + cross_bonus + contact_bonus, 100)
```

### Component 1: Source Score (0–60 points)

```
source_score = sum(W[source] × D[recency] × 100) capped at 60
```

**Authority weights (W)**:
| Source | Weight |
|--------|--------|
| Shovels (government permit) | 0.30 |
| ATTOM (recorded deed/mortgage) | 0.28 |
| CountyAssessor (tax authority) | 0.22 |
| OpenCorporates (SOS filing) | 0.20 |
| Apollo / Hunter (commercial DB) | 0.10 |
| Exa / web search | 0.05 |

**Recency decay (D)**:
```
D = max(0.30, 1.0 - (years_old × 0.14))
```
Examples: 0yr→1.0, 1yr→0.86, 3yr→0.58, 5yr→0.30 (floor)

### Component 2: Cross-Match Bonus (0–30 points)

| Independent source count | Bonus |
|--------------------------|-------|
| 1 | 0 |
| 2 | +15 |
| 3 | +25 |
| 4+ | +30 |

Remember: ATTOM + County Assessor = 1 independent group (not 2).
See `directives/03_data_sources_and_api_keys.md` for the full independence matrix.

### Component 3: Contact Completeness Bonus (0–10 points)

| Field present | Bonus |
|---------------|-------|
| Email | +5 |
| Phone | +5 |
| LinkedIn URL | +3 |
| Maximum | 10 |

## Label Thresholds

| Score | Label | What it means |
|-------|-------|---------------|
| 75–100 | **Verified** | ≥2 independent authoritative sources, recent, contact confirmed |
| 45–74 | **Probable** | ≥1 authoritative source OR 2 non-authoritative sources |
| 0–44 | **Unconfirmed** | Single source, stale data, or enrichment-only |

## Last Verified Date

Set to the date the pipeline was run (today's date).
This field should be checked on each re-run — if the sheet already has a row for this
stakeholder and Last Verified Date is within 90 days, the existing row may be reused
without re-running enrichment (saves credits). Re-run the full pipeline if >90 days old.

## Important: Scores Are Advisory

Confidence scores guide — they do not replace human judgment.
A Verified (score=80) lender name from ATTOM is factual; the phone number from Apollo
(score bonus contributor) should still be verified before calling.

## Debugging Score Anomalies

If a stakeholder has unexpected score:
1. Check `source_records` in `.tmp/scored_stakeholders.json`
2. Verify `record_date` fields are being set correctly
3. Check `independent_source_count` — if 1 when you expect 2, check independence matrix
4. Phone enrichment not happening? Check `ENRICH_PHONE_ROLES` env var
