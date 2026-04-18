# Directive 02: Address Normalization

## Rule
**ALWAYS run Smarty normalization before any other API call.**
Never pass a raw user-typed address to Shovels, ATTOM, or any downstream API.
Malformed addresses waste API credits and return zero results.

## Why
Downstream APIs (Shovels, ATTOM, county assessors) all expect standardized USPS format.
A user might type "123 main st apt 4, LA 90210" — Smarty returns "123 MAIN ST APT 4, LOS ANGELES CA 90210" with county FIPS, lat/lon, and a verification code.

## DPV Match Code Decision Tree

| Code | Meaning | Action |
|------|---------|--------|
| Y | Confirmed delivery point | Proceed normally |
| S | Confirmed, but secondary info (apt/suite) missing | Proceed with warning |
| D | Building confirmed but no matching secondary | Proceed with warning |
| N | Address not found | STOP. Ask user to verify |

## What Gets Saved
`.tmp/normalized_address.json` — StandardAddress object with:
- `delivery_line_1` — Standardized street line
- `city`, `state`, `zip5`, `zip4`
- `county_fips` — 5-digit FIPS (used by county_assessor_router.py)
- `county_name` — Human-readable county
- `latitude`, `longitude`
- `rdi` — "R" (residential) or "C" (commercial)
- `dpv_match_code` — Verification status

## Cache Behavior
If `.tmp/normalized_address.json` exists and is less than 24 hours old,
the pipeline reuses it. Use `--no-cache` to force re-normalization.

## Edge Cases
- PO Box addresses: Smarty will verify them, but permit and assessor APIs won't
  find a physical property — expect zero permit results. Warn user and proceed.
- Apartment complexes: DPV=S (missing unit). Proceed. Shovels will return permits
  for the entire building address.
- Intersections ("Main St & 1st Ave"): Smarty will return DPV=N. Ask user for a
  specific address or parcel ID.
- Rural routes ("RR 2 Box 15"): Smarty may return DPV=Y but county assessor
  coverage is unlikely. Proceed with ATTOM only.
