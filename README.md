# BillParse

Extract structured data from utility invoices (electricity, gas, water) using an LLM,
via a web UI, and export the results as CSV.

## What it does

Upload one or more utility bill PDFs — in any language, any layout — and BillParse:

1. Extracts the raw text from each PDF (`pdfplumber`).
2. Sends that text to Claude with a forced tool-use schema, so the model returns
   structured JSON instead of free-form prose.
3. Validates and coerces the result (ISO dates, numeric usage, a fixed `utility_type`
   enum) before it's ever shown to the user.
4. Shows a results table in the browser and lets you download everything as one CSV.

Output columns (the 8 required fields, plus bonus columns for language, confidence, and
per-field confidence):
`source_filename, vendor_name, invoice_date, service_address, utility_type, usage_amount,
usage_unit, billing_period_start, billing_period_end, detected_language, confidence,
status, vendor_name_confidence, invoice_date_confidence, utility_type_confidence,
usage_amount_confidence, usage_unit_confidence, billing_period_start_confidence,
billing_period_end_confidence`

`confidence` is an invoice-level summary; the `*_confidence` columns are Claude's
per-field self-report, corrected by our own validation. See "Key decisions" below for how
the two relate.

## Running it locally

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # then put your ANTHROPIC_API_KEY in .env
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000, drag in PDFs from `samples/English/`, `samples/French/`, or
`samples/Spanish/`, then click "Download CSV".

## Sample files

`samples/English/`, `samples/French/`, and `samples/Spanish/` contain 6 real-world bills
used for validation, across 3 languages:

- `Sample-Bill-8.01.2019-Sparky-Joule.pdf` — PG&E (English)
- `solar-choice-bill-sample.pdf` — a blank template with placeholder values like
  `mm/dd/yyyy` (English) — kept intentionally, see Testing Approach below
- `fichier_17_01_2023_1673982146_French_2.pdf` — a French electricity bill
- `PURA VIDA - Statuts constitutifs_French_1.pdf` — a TotalEnergies electricity bill
  (French) — misleadingly named, but real invoice content
- `Spanish_Bill1.pdf` — an Iberdrola electricity bill (Spanish)
- `Spanish_Bill2.pdf` — a scanned/image-only Spanish bill with no extractable text layer
  — kept intentionally, see Testing Approach below

`output/sample_output.csv` is the generated CSV from running all 6 of the above through
the pipeline.

**Assumption / scope note:** OCR is not implemented, per the challenge's own stated
assumption that it's not required. `Spanish_Bill2.pdf` is a real scanned PDF with zero
extractable text, kept in the sample set specifically to demonstrate the pipeline's
`no_text_found` path — it's detected before any LLM call and reported with a clear
status rather than crashing or silently skipping the file.

## Key decisions and tradeoffs

- **Structured tool-use output over prompting for JSON in prose.** Forcing a tool call
  with a strict `input_schema` means the model literally cannot return malformed JSON or
  extra commentary — no brittle regex/`json.loads` parsing of LLM text needed.
- **The LLM does date normalization, not our code.** Utility bills use `dd/mm/yyyy`,
  `mm/dd/yyyy`, and written-out dates depending on locale, and disambiguating them
  requires the surrounding language context the LLM already has. We instruct Claude to
  always emit ISO 8601, then just validate the *shape* of what comes back — we never try
  to re-parse an ambiguous date ourselves.
- **Never fabricate — null over guess.** The system prompt explicitly tells Claude that a
  missing field should be `null`, not an invented value, and that placeholder text (e.g.
  the literal string `mm/dd/yyyy` on the blank template bill) is not a real value. The
  Pydantic layer is a second line of defense: anything that isn't a valid ISO date after
  the LLM call still gets nulled rather than passed through.
- **Vanilla HTML/CSS/JS frontend, no build step.** FastAPI serves the static files
  directly. One process, one `uvicorn` command — nothing for an evaluator's machine to
  fight with (no Node/npm toolchain), while still being a genuine full-stack app (real
  HTTP API, real client-side JS driving it).
- **In-memory result store.** Results accumulate for the life of the server process; a
  `/api/reset` endpoint clears them. No database — this is a demo-scoped tool, not a
  persisted multi-user system.
- **Per-file error isolation.** One bad file in a batch (corrupt PDF, non-PDF upload,
  LLM error) doesn't fail the whole request — every other file in the batch still gets
  processed, and the bad one shows a clear status instead of a fabricated row.
- **Per-field confidence, with the invoice-level score *computed*, not independently
  self-reported.** Claude grades each of the 7 required fields individually
  (`backend/llm_extract.py`'s `field_confidence` schema property). The invoice-level
  `confidence` column is then derived in `backend/models.py::aggregate_confidence` as the
  *worst* score across those fields — a missing required field counts as worse than an
  explicit "low", so one badly-extracted field can't hide behind six good ones. Two
  deterministic overrides win over whatever Claude self-reported: (1) if our own shape
  validation nulls out a value (bad date format, unparseable number), that field's
  confidence is nulled too, regardless of what Claude claimed; (2) a billing-period
  cross-check (`apply_period_cross_check`) forces both period fields to "low" if the end
  date precedes the start date. **This changes what the `confidence` column means**
  compared to earlier versions of this project (previously: Claude's own one-shot
  self-assessment of the whole invoice; now: a computed aggregate) — same column, same
  three-value enum, but a behavior change worth knowing about if you're comparing output
  across versions. Self-reported confidence, per-field or not, is still uncalibrated —
  see "What I'd do with more time" and `TESTING.md`.

## What I'd do with more time

- Add OCR (`pytesseract` + `pdf2image`) as a fallback for zero-text/scanned PDFs — the
  pipeline already detects a zero-character extraction and reports it cleanly
  (`Spanish_Bill2.pdf` exercises this today), so OCR would slot in at that exact point
  without restructuring anything.
- Add more languages/layouts beyond the current English/French/Spanish set.
- Persist results in SQLite instead of an in-memory list, so a server restart doesn't
  lose in-progress work and multiple users don't share one global result list.
- An editable results table so a human can correct a field before exporting, rather than
  re-uploading.
- A fuller automated test suite (unit + integration + end-to-end against real sample
  invoices, run in CI) — currently only the deterministic confidence-scoring logic has
  unit tests (`tests/unit/test_confidence.py`); the rest of the pipeline is still
  validated manually (see `TESTING.md`).
- Surface per-field confidence in the UI — the results table currently shows only the
  invoice-level `confidence` column; the richer per-field breakdown is in the API/CSV but
  not yet rendered in the browser.
- Real calibration of confidence scores against a labeled dataset at scale. With only 4
  samples, "high" is a heuristic (self-report plus deterministic corrections), not a
  statistically calibrated probability — see `TESTING.md`.
- A cross-check for plausible usage magnitude vs. unit (e.g. catching a monetary total
  mistakenly extracted as `usage_amount`) — currently only the billing-period ordering is
  cross-checked, not usage plausibility.

See `TESTING.md` for how accuracy was validated and what edge cases were considered.
