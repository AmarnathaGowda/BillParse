# Testing Approach

## How accuracy was validated

There's no labeled ground-truth dataset for real-world utility bills, so validation was
manual: each of the 4 sample PDFs was run through the full pipeline and the extracted
fields were spot-checked by eye against the source PDF text (vendor name, dates, usage
figure and unit, address). See `output/sample_output.csv` for the actual output produced
this way.

Results:

| File | Language | Result |
|---|---|---|
| Sample-Bill-8.01.2019-Sparky-Joule.pdf | English | All 8 fields extracted correctly (PG&E, 380 kWh, 2019-08-02 → 2019-08-31) |
| solar-choice-bill-sample.pdf | English | Blank template — correctly returned `null` for date/usage fields instead of the literal placeholder text, flagged `confidence: low` |
| fichier_17_01_2023_1673982146_French_2.pdf | French | All 8 fields extracted correctly despite squished-together text (no spaces between words in the PDF's text layer) |
| PURA VIDA - Statuts constitutifs_French_1.pdf | French | Correctly identified as a TotalEnergies electricity bill and extracted correctly, despite a filename suggesting it's an unrelated legal document |

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
  not implemented) rather than looking like a bug. This path is exercised by construction
  (any PDF with no text layer hits it), though no such sample is included in this
  submission's scope (see README's scope note on Spanish/OCR).
- **Non-numeric usage values** — `models.py::coerce_usage_amount` nulls out anything
  that can't be parsed as a float rather than raising and failing the whole record.
- **Unknown/unrecognized `utility_type`** — normalized to `other` rather than left
  free-text, so the CSV column stays a closed set as the spec implies.
- **Batch partial failure** — one bad file in a multi-file upload doesn't affect the
  others; each file is processed and reported independently.

## Automated tests

None implemented in this submission — given the time constraints, manual verification
against the 4 real sample bills (above) was prioritized over test scaffolding, since the
main source of risk here is LLM output variability, which a unit test can't meaningfully
cover without also mocking the LLM.

## What I'd add with more time

- Unit tests for `backend/models.py`'s validators (invalid dates, non-numeric usage,
  unknown utility types, blank-string coercion) — these are pure functions and cheap to
  test properly.
- Unit tests for `backend/pdf_extract.py` against the 4 committed sample PDFs, asserting
  non-empty text extraction (a regression guard if a PDF library upgrade changes
  behavior).
- A small "golden set" of hand-labeled expected fields for the 4 samples, with a script
  that scores the pipeline's output against it — turns the current manual spot-check into
  a repeatable regression check.
- Integration tests against a mocked Anthropic client to verify the FastAPI
  request/response contract without spending real API calls on every CI run.
