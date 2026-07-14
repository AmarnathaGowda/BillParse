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

Output columns (the 8 required fields, plus 2 bonus ones):
`source_filename, vendor_name, invoice_date, service_address, utility_type, usage_amount,
usage_unit, billing_period_start, billing_period_end, detected_language, confidence, status`

## Running it locally

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # then put your ANTHROPIC_API_KEY in .env
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000, drag in PDFs from `samples/English/` or `samples/French/`,
then click "Download CSV".

## Sample files

`samples/English/` and `samples/French/` contain 4 real-world bills used for validation:

- `Sample-Bill-8.01.2019-Sparky-Joule.pdf` — PG&E (English)
- `solar-choice-bill-sample.pdf` — a blank template with placeholder values like
  `mm/dd/yyyy` (English) — kept intentionally, see Testing Approach below
- `fichier_17_01_2023_1673982146_French_2.pdf` — a French electricity bill
- `PURA VIDA - Statuts constitutifs_French_1.pdf` — a TotalEnergies electricity bill
  (French) — misleadingly named, but real invoice content

`output/sample_output.csv` is the generated CSV from running all 4 of the above through
the pipeline.

**Assumption / scope note:** Spanish samples were dropped from this submission's scope
by explicit choice, to keep the working set to two languages (English, French) and avoid
a scanned/image-only PDF that would need OCR (out of scope per the challenge's own
assumption that OCR is not required). The pipeline itself is not English/French-specific
— Claude's extraction prompt is language-agnostic, so adding another language back is a
matter of adding samples, not code changes.

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

## What I'd do with more time

- Add OCR (`pytesseract` + `pdf2image`) as a fallback for zero-text/scanned PDFs — the
  pipeline already detects a zero-character extraction and reports it cleanly, so OCR
  would slot in at that exact point without restructuring anything.
- Re-add Spanish (and more languages) samples now that OCR would cover scanned inputs too.
- Persist results in SQLite instead of an in-memory list, so a server restart doesn't
  lose in-progress work and multiple users don't share one global result list.
- An editable results table so a human can correct a field before exporting, rather than
  re-uploading.
- Automated tests (see `TESTING.md`) for the validation/coercion layer and PDF extraction
  shape, run in CI.
- Per-field confidence instead of one overall confidence per invoice.

See `TESTING.md` for how accuracy was validated and what edge cases were considered.
