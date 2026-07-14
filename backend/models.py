import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UTILITY_TYPES = {"electricity", "gas", "water", "other"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}

# Fields whose confidence feeds the invoice-level `confidence` aggregate.
# service_address is excluded (spec: "if available"); detected_language is
# metadata about the document, not an extracted invoice fact.
REQUIRED_FIELDS = (
    "vendor_name",
    "invoice_date",
    "utility_type",
    "usage_amount",
    "usage_unit",
    "billing_period_start",
    "billing_period_end",
)

# Ranks used to pick the "worst" confidence across fields. A missing value
# ranks below an explicit "low" -- a required fact that's flat-out absent
# shouldn't be able to hide behind six well-extracted fields.
_CONFIDENCE_RANK = {None: 0, "low": 1, "medium": 2, "high": 3}


def normalize_confidence(value) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized in CONFIDENCE_LEVELS else None


def null_out_missing_field_confidence(field_confidence: dict, values: dict) -> dict:
    """A field with no value can't have a meaningful confidence in that value."""
    return {
        field: (None if values.get(field) is None else field_confidence.get(field))
        for field in REQUIRED_FIELDS
    }


def apply_period_cross_check(
    field_confidence: dict, start: Optional[str], end: Optional[str]
) -> dict:
    """Force both billing-period fields to 'low' if the end precedes the start.

    ISO 8601 (YYYY-MM-DD) strings compare lexicographically the same as
    chronologically, so a plain string comparison is enough here.
    """
    result = dict(field_confidence)
    if start and end and end < start:
        if result.get("billing_period_start") is not None:
            result["billing_period_start"] = "low"
        if result.get("billing_period_end") is not None:
            result["billing_period_end"] = "low"
    return result


def aggregate_confidence(field_confidence: dict) -> str:
    """Invoice-level confidence: the worst rank among REQUIRED_FIELDS, folded to a label.

    A missing required field is treated as worse than an explicit "low", but the
    invoice-level label itself always resolves to one of high/medium/low.
    """
    worst_rank = min(_CONFIDENCE_RANK[field_confidence.get(field)] for field in REQUIRED_FIELDS)
    if worst_rank <= 1:
        return "low"
    if worst_rank == 2:
        return "medium"
    return "high"


class InvoiceRecord(BaseModel):
    vendor_name: Optional[str] = None
    invoice_date: Optional[str] = None
    service_address: Optional[str] = None
    utility_type: Optional[str] = None
    usage_amount: Optional[float] = None
    usage_unit: Optional[str] = None
    billing_period_start: Optional[str] = None
    billing_period_end: Optional[str] = None
    detected_language: Optional[str] = None
    field_confidence: dict[str, Optional[str]] = {}
    confidence: Optional[str] = None  # computed in compute_confidence, see below

    @field_validator("invoice_date", "billing_period_start", "billing_period_end")
    @classmethod
    def validate_iso_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not ISO_DATE_RE.match(value):
            return None
        return value

    @field_validator("utility_type")
    @classmethod
    def validate_utility_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized if normalized in UTILITY_TYPES else "other"

    @field_validator("vendor_name", "service_address", "usage_unit", "detected_language", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("usage_amount", mode="before")
    @classmethod
    def coerce_usage_amount(cls, value):
        if value is None or isinstance(value, (int, float)):
            return value
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    @field_validator("field_confidence", mode="before")
    @classmethod
    def normalize_field_confidence(cls, value) -> dict:
        raw = value if isinstance(value, dict) else {}
        return {field: normalize_confidence(raw.get(field)) for field in REQUIRED_FIELDS}

    @model_validator(mode="after")
    def compute_confidence(self) -> "InvoiceRecord":
        values = {field: getattr(self, field) for field in REQUIRED_FIELDS}
        field_confidence = null_out_missing_field_confidence(self.field_confidence, values)
        field_confidence = apply_period_cross_check(
            field_confidence, self.billing_period_start, self.billing_period_end
        )
        self.field_confidence = field_confidence
        self.confidence = aggregate_confidence(field_confidence)
        return self


CSV_FIELDNAMES = [
    "source_filename",
    "vendor_name",
    "invoice_date",
    "service_address",
    "utility_type",
    "usage_amount",
    "usage_unit",
    "billing_period_start",
    "billing_period_end",
    "detected_language",
    "confidence",
    "status",
    "vendor_name_confidence",
    "invoice_date_confidence",
    "utility_type_confidence",
    "usage_amount_confidence",
    "usage_unit_confidence",
    "billing_period_start_confidence",
    "billing_period_end_confidence",
]
