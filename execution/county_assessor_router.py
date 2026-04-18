"""
County Assessor Router

Maps a 5-digit county FIPS code to an AssessorConfig describing how to call
that county's public API. Returns None for unsupported counties (the fetch
script will skip gracefully).

Only counties with documented public APIs or open data endpoints are included.
No HTML scraping of government portals.

Add new counties by appending to COUNTY_CONFIGS below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AssessorConfig:
    county_name: str
    fips: str
    method: str                   # "GET" or "POST"
    endpoint_url: str
    params_template: dict[str, str]  # placeholders: {address}, {zip5}
    result_path: str              # dot-notation path to owner record in JSON response
    field_map: dict[str, str]     # maps our fields to API field names


# ── Known county configs ──────────────────────────────────────────────────────
# Add counties by their 5-digit FIPS code.
# params_template values may use {address} and {zip5} as placeholders.

COUNTY_CONFIGS: dict[str, AssessorConfig] = {

    # Los Angeles County, CA
    "06037": AssessorConfig(
        county_name="Los Angeles County, CA",
        fips="06037",
        method="GET",
        endpoint_url="https://assessor.lacounty.gov/api/search/address",
        params_template={"address": "{address}", "zip": "{zip5}"},
        result_path="results.0",
        field_map={
            "owner_name": "ownerName",
            "mailing_address": "mailingAddress",
            "assessed_value": "totalValue",
            "parcel_id": "ain",
            "land_use_code": "useType",
        },
    ),

    # Cook County, IL (Chicago)
    "17031": AssessorConfig(
        county_name="Cook County, IL",
        fips="17031",
        method="GET",
        endpoint_url="https://datacatalog.cookcountyil.gov/resource/bcnq-qi2z.json",
        params_template={"property_address": "{address}"},
        result_path="0",
        field_map={
            "owner_name": "taxpayer_name",
            "mailing_address": "mailing_address",
            "assessed_value": "assessed_value",
            "parcel_id": "pin",
            "land_use_code": "class",
        },
    ),

    # Harris County, TX (Houston)
    "48201": AssessorConfig(
        county_name="Harris County, TX",
        fips="48201",
        method="GET",
        endpoint_url="https://api.hcad.org/property/address",
        params_template={"addr": "{address}", "zip": "{zip5}"},
        result_path="data.0",
        field_map={
            "owner_name": "owner_name",
            "mailing_address": "mail_address_1",
            "assessed_value": "appraised_val",
            "parcel_id": "account",
            "land_use_code": "state_class",
        },
    ),

    # Maricopa County, AZ (Phoenix)
    "04013": AssessorConfig(
        county_name="Maricopa County, AZ",
        fips="04013",
        method="GET",
        endpoint_url="https://mcassessor.maricopa.gov/mcs.php",
        params_template={"q": "{address} {zip5}"},
        result_path="items.0",
        field_map={
            "owner_name": "owner_name",
            "mailing_address": "mail_addr",
            "assessed_value": "lsvfv",
            "parcel_id": "apn",
            "land_use_code": "use_code",
        },
    ),

    # King County, WA (Seattle)
    "53033": AssessorConfig(
        county_name="King County, WA",
        fips="53033",
        method="GET",
        endpoint_url="https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_Parcels/MapServer/0/query",
        params_template={
            "where": "SITUS_ADDRESS='{address}'",
            "outFields": "PIN,OWNER_NAME,MAILING_ADDRESS,APPRAISED_VALUE,LAND_USE",
            "f": "json",
            "returnGeometry": "false",
        },
        result_path="features.0.attributes",
        field_map={
            "owner_name": "OWNER_NAME",
            "mailing_address": "MAILING_ADDRESS",
            "assessed_value": "APPRAISED_VALUE",
            "parcel_id": "PIN",
            "land_use_code": "LAND_USE",
        },
    ),

    # New York City (Manhattan / NYC boroughs use citywide open data)
    # Covers FIPS: 36005 (Bronx), 36047 (Brooklyn), 36061 (Manhattan),
    #              36081 (Queens), 36085 (Staten Island)
    "36061": AssessorConfig(
        county_name="New York County (Manhattan), NY",
        fips="36061",
        method="GET",
        endpoint_url="https://data.cityofnewyork.us/resource/8y4t-faws.json",
        params_template={"address": "{address}", "zipcode": "{zip5}"},
        result_path="0",
        field_map={
            "owner_name": "owner",
            "mailing_address": "mailadd",
            "assessed_value": "assesstot",
            "parcel_id": "bbl",
            "land_use_code": "landuse",
        },
    ),
    "36047": AssessorConfig(
        county_name="Kings County (Brooklyn), NY",
        fips="36047",
        method="GET",
        endpoint_url="https://data.cityofnewyork.us/resource/8y4t-faws.json",
        params_template={"address": "{address}", "zipcode": "{zip5}"},
        result_path="0",
        field_map={
            "owner_name": "owner",
            "mailing_address": "mailadd",
            "assessed_value": "assesstot",
            "parcel_id": "bbl",
            "land_use_code": "landuse",
        },
    ),
    "36081": AssessorConfig(
        county_name="Queens County, NY",
        fips="36081",
        method="GET",
        endpoint_url="https://data.cityofnewyork.us/resource/8y4t-faws.json",
        params_template={"address": "{address}", "zipcode": "{zip5}"},
        result_path="0",
        field_map={
            "owner_name": "owner",
            "mailing_address": "mailadd",
            "assessed_value": "assesstot",
            "parcel_id": "bbl",
            "land_use_code": "landuse",
        },
    ),

    # Miami-Dade County, FL
    "12086": AssessorConfig(
        county_name="Miami-Dade County, FL",
        fips="12086",
        method="GET",
        endpoint_url="https://opendata.miamidade.gov/resource/9bfj-3vn6.json",
        params_template={"property_address": "{address}", "zip_code": "{zip5}"},
        result_path="0",
        field_map={
            "owner_name": "owner1",
            "mailing_address": "mailing_address",
            "assessed_value": "tot_val",
            "parcel_id": "folio",
            "land_use_code": "dor_uc",
        },
    ),

    # Dallas County, TX
    "48113": AssessorConfig(
        county_name="Dallas County, TX",
        fips="48113",
        method="GET",
        endpoint_url="https://www.dallascad.org/api/AcctSearch.aspx",
        params_template={"s": "{address}", "t": "A"},
        result_path="0",
        field_map={
            "owner_name": "owner_name",
            "mailing_address": "mail_addr",
            "assessed_value": "tot_val",
            "parcel_id": "acct_num",
            "land_use_code": "land_use",
        },
    ),

    # Travis County, TX (Austin)
    "48453": AssessorConfig(
        county_name="Travis County, TX",
        fips="48453",
        method="GET",
        endpoint_url="https://traviscad.org/api/property/search",
        params_template={"address": "{address}", "zip": "{zip5}"},
        result_path="properties.0",
        field_map={
            "owner_name": "ownerName",
            "mailing_address": "mailingAddress",
            "assessed_value": "appraisedValue",
            "parcel_id": "propertyId",
            "land_use_code": "landUseCode",
        },
    ),
}


# Mirror NYC FIPs variants
COUNTY_CONFIGS["36005"] = COUNTY_CONFIGS["36061"]  # Bronx
COUNTY_CONFIGS["36085"] = COUNTY_CONFIGS["36061"]  # Staten Island


def get_config(county_fips: str) -> AssessorConfig | None:
    """Return AssessorConfig for the given FIPS, or None if unsupported."""
    return COUNTY_CONFIGS.get(county_fips)


def resolve_value(data: Any, dot_path: str) -> Any:
    """
    Navigate a dot-notation path through nested dicts/lists.
    E.g. 'features.0.attributes' on {"features": [{"attributes": {...}}]}
    """
    parts = dot_path.split(".")
    current = data
    for part in parts:
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
