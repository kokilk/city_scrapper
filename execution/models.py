"""
Shared dataclasses for the real estate stakeholder intelligence pipeline.
All execution scripts import from this module. This is the schema contract
between pipeline stages — change here propagates everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


# ── Stage 0: Address ─────────────────────────────────────────────────────────

@dataclass
class StandardAddress:
    delivery_line_1: str        # "123 MAIN ST STE 200"
    city: str
    state: str                  # 2-letter abbreviation
    zip5: str
    zip4: str                   # may be empty string
    county_fips: str            # 5-digit, e.g. "06037"
    county_name: str
    latitude: float
    longitude: float
    rdi: str                    # "R" residential, "C" commercial, "" unknown
    dpv_match_code: str         # "Y" exact, "S" secondary, "D" missing secondary, "N" none
    raw_input_address: str
    raw_input_zip: str

    def slug(self) -> str:
        """URL/filename-safe slug: '123MainSt90210'"""
        import re
        base = f"{self.delivery_line_1}{self.zip5}"
        return re.sub(r"[^A-Za-z0-9]", "", base.title())

    def full(self) -> str:
        return f"{self.delivery_line_1}, {self.city}, {self.state} {self.zip5}"


# ── Stage 1: Raw API records ──────────────────────────────────────────────────

@dataclass
class SourceReference:
    source_name: str            # "Shovels", "ATTOM", "OpenCorporates", etc.
    record_id: str              # permit number, parcel ID, company number, etc.
    record_date: date           # most relevant date for this record
    raw_url: str = ""           # API endpoint or data URL for audit


@dataclass
class PermitRecord:
    permit_id: str
    file_date: date | None
    issue_date: date | None
    job_value: float | None
    status: str
    permit_type: str            # from TAGS field
    # Permit applicant (often owner or developer)
    applicant_name: str
    applicant_email: str
    applicant_phone: str
    # Property owner on permit
    owner_name: str
    owner_email: str
    owner_phone: str
    # Contractor of record
    contractor_id: str
    source: SourceReference = field(default_factory=lambda: SourceReference("Shovels", "", date.today()))


@dataclass
class ContractorProfile:
    contractor_id: str
    biz_name: str
    classification_derived: str  # "general", "electrical", "architect", etc.
    primary_email: str
    primary_phone: str
    website: str
    linkedin_url: str
    license_number: str
    license_exp_date: date | None
    license_status: str         # "Active", "Expired", "Suspended"
    permit_count: int
    avg_job_value: float | None
    source: SourceReference = field(default_factory=lambda: SourceReference("Shovels", "", date.today()))


@dataclass
class PropertyRecord:
    owner_full_name: str
    owner_mailing_address: str
    lender_name: str
    loan_amount: float | None
    loan_type: str
    loan_term: str
    last_sale_date: date | None
    last_sale_price: float | None
    deed_type: str
    source: SourceReference = field(default_factory=lambda: SourceReference("ATTOM", "", date.today()))


@dataclass
class CompanyOfficer:
    name: str
    position: str               # "director", "agent", "managing member", etc.
    start_date: date | None
    end_date: date | None       # None = current
    address: str


@dataclass
class CompanyRecord:
    company_name: str
    company_number: str
    jurisdiction: str           # e.g. "us_ca"
    company_type: str           # "LLC", "Corporation", etc.
    incorporation_date: date | None
    status: str                 # "Active", "Dissolved", etc.
    registered_agent: str
    officers: list[CompanyOfficer] = field(default_factory=list)
    source: SourceReference = field(default_factory=lambda: SourceReference("OpenCorporates", "", date.today()))


@dataclass
class AssessorRecord:
    owner_name: str
    mailing_address: str
    assessed_value: float | None
    parcel_id: str
    land_use_code: str
    source: SourceReference = field(default_factory=lambda: SourceReference("CountyAssessor", "", date.today()))


# ── Stage 2: Extracted stakeholders ──────────────────────────────────────────

StakeholderRole = Literal[
    "Developer", "Architect", "GC", "Subcontractor", "Lender", "Owner", "Unknown"
]

INDEPENDENT_SOURCE_GROUPS: dict[str, str] = {
    # Map source_name → independence group.
    # Sources in the same group are NOT independent of each other.
    "Shovels": "permit",
    "ATTOM": "deed",
    "CountyAssessor": "deed",        # same lineage as ATTOM (both from recorded deed)
    "OpenCorporates": "sos",
    "Apollo": "contact_db",
    "Hunter": "contact_db",          # same lineage as Apollo
    "Exa": "web",
}


@dataclass
class StakeholderCandidate:
    raw_name: str
    role: StakeholderRole
    company: str
    source_records: list[SourceReference] = field(default_factory=list)
    first_seen_date: date = field(default_factory=date.today)
    flags: list[str] = field(default_factory=list)  # SINGLE_SOURCE, LLC_UNRESOLVED, etc.

    def independent_source_count(self) -> int:
        groups = {
            INDEPENDENT_SOURCE_GROUPS.get(s.source_name, s.source_name)
            for s in self.source_records
        }
        return len(groups)


# ── Stage 3: Enriched stakeholders ───────────────────────────────────────────

@dataclass
class EnrichedStakeholder(StakeholderCandidate):
    email: str = ""
    phone: str = ""             # E.164 format: +15551234567
    linkedin_url: str = ""
    website: str = ""
    email_confidence: int = 0   # Apollo or Hunter confidence (0-100)
    enrichment_sources: list[str] = field(default_factory=list)


# ── Stage 4: Cross-verified ────────────────────────────────────────────────

@dataclass
class VerifiedStakeholder(EnrichedStakeholder):
    verification_status: Literal["cross_verified", "single_source"] = "single_source"


# ── Stage 5: Scored ────────────────────────────────────────────────────────

@dataclass
class ScoredStakeholder(VerifiedStakeholder):
    confidence_score: float = 0.0   # 0–100
    confidence_label: Literal["Verified", "Probable", "Unconfirmed"] = "Unconfirmed"

    # Permit fields (from Shovels, denormalized for sheet output)
    permit_number: str = ""
    permit_date: date | None = None
    permit_type: str = ""
    permit_value: float | None = None
    license_number: str = ""
    license_status: str = ""
    license_expiry: date | None = None

    # Property fields (denormalized for sheet output)
    property_address: str = ""
    county_fips: str = ""
    attom_lender: str = ""
    attom_loan_amount: float | None = None

    last_verified_date: date = field(default_factory=date.today)
    stakeholder_id: str = ""    # UUID assigned at dedup stage


# ── Source status (pipeline health) ──────────────────────────────────────────

@dataclass
class SourceStatus:
    source_name: str
    status: Literal["ok", "empty", "failed", "skipped"]
    message: str = ""
    records_fetched: int = 0
