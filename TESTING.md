# Testing Approach

## How accuracy was validated

There's no labeled ground-truth dataset for real-world utility bills, so validation was
manual: each of the 6 sample PDFs was run through the full pipeline and the extracted
fields were spot-checked by eye against the source PDF text (vendor name, dates, usage
figure and unit, address). See `output/sample_output.csv` for the actual output produced
this way.

Results:

| File | Language | Result |
|---|---|---|
| Sample-Bill-8.01.2019-Sparky-Joule.pdf | English | All 7 required fields extracted correctly (PG&E, 380 kWh, 2019-08-02 → 2019-08-31), all `high` per-field confidence, invoice `confidence: high` |
| solar-choice-bill-sample.pdf | English | Blank template — correctly returned `null` for date/usage fields instead of the literal placeholder text; every field's confidence is `null` (no value to grade), and the invoice-level `confidence` computes to `low` because required fields are missing |
| fichier_17_01_2023_1673982146_French_2.pdf | French | All 7 required fields extracted correctly despite squished-together text (no spaces between words in the PDF's text layer); `usage_amount` came back `medium` confidence on one run, correctly pulling the invoice-level `confidence` down to `medium` even though every other field was `high` — exactly the scenario per-field scoring is meant to surface |
| PURA VIDA - Statuts constitutifs_French_1.pdf | French | Correctly identified as a TotalEnergies electricity bill, despite a filename suggesting it's an unrelated legal document |
| Spanish_Bill1.pdf | Spanish | All 7 required fields extracted correctly (Iberdrola, 350 kWh, 2018-05-08 → 2018-06-10), all `high` per-field confidence |
| Spanish_Bill2.pdf | Spanish (unknown — no text) | Zero extractable text (pdfplumber returns `""`) — correctly short-circuits to `status: no_text_found` before any LLM call, with a clear reason shown in the UI, instead of erroring or silently skipping the file |

**Observed limitation of self-reported confidence:** on repeated runs against `PURA VIDA
- Statuts constitutifs_French_1.pdf`, `usage_amount` came back as two different values
across two separate API calls (3736 vs. 4739 kWh — the source text states an "index de
compteur" of 4739 kWh, a cumulative meter reading that isn't unambiguously the same thing
as period consumption). Both runs self-reported `high` confidence for that field. This is
a real, observed example of why per-field self-report is a heuristic, not a calibrated
probability — the model was equally "confident" while giving two different answers. It's
documented here rather than hidden, and is the reason `README.md` and the confidence
design don't claim the scores are statistically calibrated.

## Edge cases considered

- **Missing/ambiguous fields** — `solar-choice-bill-sample.pdf` is a real sample that
  exercises this directly: it's a blank template containing only placeholder text like
  `mm/dd/yyyy` and `PAT DOE`. The system prompt explicitly tells Claude not to treat
  placeholder text as a real value, and the Pydantic layer independently rejects any
  `invoice_date`/`billing_period_*` value that isn't a valid `YYYY-MM-DD` string,
  regardless of what the LLM returned. One residual limitation: the template's
  placeholder *address* (`1234 MAIN STREET, ANYTOWN, CA 12345`) is plausible-looking
  enough that it passes through — free-text fields like address can't be validated by
  shape the way dates and numbers can.
- **Non-PDF upload** — rejected before any processing, per-file, with a clear
  `error` status (`backend/main.py::_process_file`).
- **Empty file (0 bytes)** — rejected the same way, before ever calling pdfplumber.
- **Corrupt/unreadable PDF** — caught around `pdf_extract.extract_text`, surfaced as an
  `error` status with the underlying exception message rather than crashing the batch.
- **Zero extractable text (scanned/image-only PDF)** — detected as a distinct
  `no_text_found` status, separate from a hard error, so the UI can explain *why* (OCR
  not implemented) rather than looking like a bug. Exercised by a real sample,
  `Spanish_Bill2.pdf`, which pdfplumber extracts as `""`.
- **Non-numeric usage values** — `models.py::coerce_usage_amount` nulls out anything
  that can't be parsed as a float rather than raising and failing the whole record.
- **Unknown/unrecognized `utility_type`** — normalized to `other` rather than left
  free-text, so the CSV column stays a closed set as the spec implies.
- **Batch partial failure** — one bad file in a multi-file upload doesn't affect the
  others; each file is processed and reported independently.
- **Confidence claimed for a field that has no value** — if Claude self-reports a
  confidence for a field it actually returned `null` for (or that our own validation
  nulled out), that confidence is discarded rather than shown, since a confidence label on
  a missing value isn't meaningful (`models.py::null_out_missing_field_confidence`).
- **Self-reported confidence surviving a value our own validation rejected** — if Claude
  reports `high` confidence for a date string that fails ISO-shape validation, the
  rejection wins: the field is nulled, and so is its confidence, regardless of the
  self-report. Covered by
  `tests/unit/test_confidence.py::test_invoice_record_forces_low_when_validation_rejects_a_value`.
- **Internally inconsistent billing period** — a billing period whose end date precedes
  its start date is caught by `models.py::apply_period_cross_check`, which forces both
  fields' confidence to `low` regardless of self-report. Covered by
  `tests/unit/test_confidence.py::test_invoice_record_applies_period_cross_check`.

## Automated tests

`tests/unit/test_confidence.py` (12 tests, `pytest`) covers the per-field confidence
logic added in `backend/models.py`: normalizing raw confidence strings, nulling out
confidence for fields with no value, the billing-period cross-check, the
worst-score-wins aggregation (including the "missing ranks worse than low" rule), and the
end-to-end behavior through `InvoiceRecord` (including validation-driven downgrades).
These are pure functions or pure-function-shaped model logic, so no LLM mocking is
needed — run them with:

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```

Everything else in the pipeline (PDF extraction, the LLM call itself, the FastAPI
endpoints, CSV export) is still validated manually against the 6 real sample bills
(above), not by automated tests — that remains the largest gap, see below.

## What I'd add with more time

- Unit tests for `backend/models.py`'s *other* validators (invalid dates, non-numeric
  usage, unknown utility types, blank-string coercion) — only the confidence-scoring
  logic has tests so far; these are equally pure and cheap to test.
- Unit tests for `backend/pdf_extract.py` against the 6 committed sample PDFs, asserting
  non-empty text extraction (a regression guard if a PDF library upgrade changes
  behavior).
- A small "golden set" of hand-labeled expected fields for the 6 samples — including an
  expected confidence floor per field — with a script that scores the pipeline's output
  against it. Turns both the manual accuracy spot-check *and* the confidence sanity-check
  above into a repeatable regression check, rather than something re-verified by eye each
  time.
- Integration tests against a mocked Anthropic client to verify the FastAPI
  request/response contract without spending real API calls on every CI run.
- A cross-check for plausible usage magnitude vs. unit, alongside the existing
  billing-period ordering check — would have caught, or at least flagged, the
  usage_amount variability observed above.
- Real calibration of confidence scores ("of everything marked `high`, what fraction is
  actually correct?") against a labeled dataset large enough to be statistically
  meaningful — not achievable with 6 samples, noted honestly rather than implied.
