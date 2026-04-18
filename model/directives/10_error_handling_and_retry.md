# Directive 10: Error Handling and Retry

## Core Principle: Never Crash on a Single API Failure

Each Stage 1 source writes its own output file. If one source fails, the pipeline continues with remaining sources. A property with only Shovels data is more useful than no output at all.

## Retry Configuration (api_client.py)

- Max retries: 5
- Backoff: exponential with jitter (base=1s, max=60s)
- Retry on: 429, 500, 502, 503, 504
- Respect `Retry-After` header on 429 responses
- Give up immediately on: 400, 401, 403, 404, 422

## Per-Source Failure Behavior

| Source | On Failure | Output File |
|--------|-----------|-------------|
| Smarty (Stage 0) | STOP pipeline — can't proceed without normalized address | N/A |
| Shovels permits | Log, write `[]` to output | shovels_permits.json = [] |
| Shovels contractors | Log, write `{}` to output | shovels_contractors.json = {} |
| ATTOM | Log, write `{"_status": "FAILED"}` | attom_property.json |
| OpenCorporates | Log, write `{}` to output | opencorporates_entities.json = {} |
| County Assessor | Log, write `{"_status": "SKIPPED"}` | county_assessor.json |
| Apollo | Log, skip enrichment for this candidate | contact fields stay empty |
| Hunter | Log, skip Hunter for this candidate | contact fields stay empty |
| Google Sheets | Log, exit 1 — report to user | N/A |

## Log Files

- `.tmp/api_calls.log` — every API call with timestamp, URL, status, latency
- `.tmp/run_summary.json` — final execution summary with source_statuses
- `stderr` — all error messages printed with `[script_name] ERROR:` prefix

## When to Self-Anneal

If a script fails due to an unexpected API response format (new field names, changed schema):
1. Read the error in `.tmp/api_calls.log` or stderr
2. Find the relevant raw response (add a `print(data)` debug line temporarily)
3. Fix the field mapping in the execution script
4. Re-run: `python execution/pipeline_runner.py --address "..." --zip "..." --no-cache`
5. Update this directive with the discovered change

## When to Stop and Ask the User

- Stage 0 fails (undeliverable address)
- ALL Stage 1 sources fail simultaneously (likely a network issue or all keys are invalid)
- Google Sheets write fails due to missing credentials.json
- OpenCorporates daily limit reached in the middle of a run (data is partial)
