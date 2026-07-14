import re
from typing import Optional

from pydantic import BaseModel, field_validator

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UTILITY_TYPES = {"electricity", "gas", "water", "other"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}


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
    confidence: Optional[str] = None

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

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized if normalized in CONFIDENCE_LEVELS else None

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
]
