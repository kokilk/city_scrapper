# Directive 11: .tmp Directory and Cache

## Purpose

`.tmp/` holds all intermediate files generated during a pipeline run.
These files are the contract between stages — each stage reads previous stages' output
from `.tmp/` rather than receiving data as function arguments.

## File Map

| File | Written by | Read by | Contains |
|------|-----------|---------|---------|
| `normalized_address.json` | normalize_address.py | All Stage 1 scripts | StandardAddress |
| `shovels_permits.json` | shovels_permit_fetch.py | shovels_contractor_fetch, entity_extractor, opencorporates | List of PermitRecord dicts |
| `shovels_contractors.json` | shovels_contractor_fetch.py | entity_extractor | Dict keyed by contractor_id |
| `attom_property.json` | attom_property_fetch.py | entity_extractor, opencorporates | PropertyRecord dict |
| `opencorporates_entities.json` | opencorporates_entity_lookup.py | entity_extractor | Dict keyed by entity_name |
| `county_assessor.json` | county_assessor_fetch.py | entity_extractor | AssessorRecord dict |
| `opencorporates_usage.json` | opencorporates_entity_lookup.py | Same | Daily request counter |
| `stakeholder_candidates.json` | entity_extractor.py | contact_enricher | List of StakeholderCandidate |
| `enriched_stakeholders.json` | contact_enricher.py | cross_verifier | List with email/phone/LinkedIn |
| `verified_stakeholders.json` | cross_verifier.py | confidence_scorer | List with verification_status |
| `scored_stakeholders.json` | confidence_scorer.py | deduplicator | List with confidence_score |
| `final_stakeholders.json` | deduplicator.py | sheets_writer | Final deduplicated list |
| `api_calls.log` | api_client.py | Human review | Every API call log |
| `run_summary.json` | pipeline_runner.py | Human review | Run stats and source statuses |

## Cache Behavior

Stage 1 files are cached for 24 hours. If the same address is queried again within 24 hours,
the pipeline reuses existing `.tmp/` files and skips all Stage 1 API calls.

This saves API credits when:
- Re-running after an enrichment failure
- Re-running after fixing a parsing bug in entity_extractor.py
- Testing changes to downstream stages

**To bypass cache**: `python execution/pipeline_runner.py --address "..." --zip "..." --no-cache`

`opencorporates_usage.json` is NOT cleared by `--no-cache` — it persists to enforce the daily limit.

## What NOT to Commit

`.tmp/` should be in `.gitignore`. It contains:
- Personal data (names, emails, phones) — CCPA-sensitive
- API responses with potentially licensed data (Shovels, ATTOM)
- Temporary state that is always regenerated

## Cleanup

`.tmp/` can be safely deleted at any time. The next pipeline run will regenerate all files.
Do not delete `.tmp/opencorporates_usage.json` during the same calendar day — it tracks daily usage limits.
