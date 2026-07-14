from backend.models import (
    REQUIRED_FIELDS,
    InvoiceRecord,
    aggregate_confidence,
    apply_period_cross_check,
    normalize_confidence,
    null_out_missing_field_confidence,
)

ALL_HIGH = {field: "high" for field in REQUIRED_FIELDS}


def test_normalize_confidence_accepts_valid_levels_case_insensitively():
    assert normalize_confidence("High") == "high"
    assert normalize_confidence(" low ") == "low"


def test_normalize_confidence_rejects_unknown_values():
    assert normalize_confidence("very sure") is None
    assert normalize_confidence(None) is None


def test_null_out_missing_field_confidence_nulls_fields_with_no_value():
    # The model claimed "high" confidence, but the value itself is missing --
    # a self-report about a value that doesn't exist isn't meaningful.
    field_confidence = dict(ALL_HIGH)
    values = {field: "some value" for field in REQUIRED_FIELDS}
    values["invoice_date"] = None

    result = null_out_missing_field_confidence(field_confidence, values)

    assert result["invoice_date"] is None
    assert result["vendor_name"] == "high"


def test_apply_period_cross_check_downgrades_when_end_precedes_start():
    field_confidence = dict(ALL_HIGH)

    result = apply_period_cross_check(field_confidence, start="2024-06-01", end="2024-05-01")

    assert result["billing_period_start"] == "low"
    assert result["billing_period_end"] == "low"


def test_apply_period_cross_check_leaves_valid_ordering_untouched():
    field_confidence = dict(ALL_HIGH)

    result = apply_period_cross_check(field_confidence, start="2024-05-01", end="2024-06-01")

    assert result["billing_period_start"] == "high"
    assert result["billing_period_end"] == "high"


def test_apply_period_cross_check_does_not_resurrect_null_fields():
    field_confidence = dict(ALL_HIGH)
    field_confidence["billing_period_start"] = None

    result = apply_period_cross_check(field_confidence, start=None, end="2024-01-01")

    # start has no value at all, so it stays null rather than becoming "low"
    assert result["billing_period_start"] is None


def test_aggregate_confidence_is_high_when_all_fields_high():
    assert aggregate_confidence(ALL_HIGH) == "high"


def test_aggregate_confidence_takes_the_worst_explicit_score():
    field_confidence = dict(ALL_HIGH)
    field_confidence["usage_amount"] = "medium"

    assert aggregate_confidence(field_confidence) == "medium"


def test_aggregate_confidence_treats_missing_field_as_worse_than_low():
    field_confidence = dict(ALL_HIGH)
    field_confidence["usage_amount"] = "low"
    field_confidence["vendor_name"] = None  # missing entirely

    # Both a missing field and an explicit "low" field are present; the
    # aggregate should still land on "low" (the worst available label),
    # not crash or treat the missing field as better than "low".
    assert aggregate_confidence(field_confidence) == "low"


def test_invoice_record_computes_confidence_end_to_end():
    record = InvoiceRecord(
        vendor_name="Acme Power",
        invoice_date="2024-01-15",
        utility_type="electricity",
        usage_amount=100,
        usage_unit="kWh",
        billing_period_start="2024-01-01",
        billing_period_end="2024-01-31",
        field_confidence={field: "high" for field in REQUIRED_FIELDS},
    )

    assert record.confidence == "high"
    assert record.field_confidence["vendor_name"] == "high"


def test_invoice_record_forces_low_when_validation_rejects_a_value():
    # invoice_date is not valid ISO 8601, so validate_iso_date nulls it out --
    # the model's "high" self-report for it must not survive that.
    record = InvoiceRecord(
        vendor_name="Acme Power",
        invoice_date="mm/dd/yyyy",
        utility_type="electricity",
        usage_amount=100,
        usage_unit="kWh",
        billing_period_start="2024-01-01",
        billing_period_end="2024-01-31",
        field_confidence={field: "high" for field in REQUIRED_FIELDS},
    )

    assert record.invoice_date is None
    assert record.field_confidence["invoice_date"] is None
    assert record.confidence == "low"


def test_invoice_record_applies_period_cross_check():
    record = InvoiceRecord(
        vendor_name="Acme Power",
        invoice_date="2024-01-15",
        utility_type="electricity",
        usage_amount=100,
        usage_unit="kWh",
        billing_period_start="2024-06-01",
        billing_period_end="2024-05-01",  # end before start
        field_confidence={field: "high" for field in REQUIRED_FIELDS},
    )

    assert record.field_confidence["billing_period_start"] == "low"
    assert record.field_confidence["billing_period_end"] == "low"
    assert record.confidence == "low"
