from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.csv_export import rows_to_csv
from backend.llm_extract import extract_invoice_fields
from backend.models import InvoiceRecord
from backend.pdf_extract import extract_text

load_dotenv()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="BillParse")

# Accumulates every processed row for the lifetime of the server process,
# so /api/export.csv can export everything extracted so far in the demo.
RESULTS: list[dict] = []


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/extract")
async def extract(files: list[UploadFile]):
    new_rows = []
    for upload in files:
        row = await _process_file(upload)
        RESULTS.append(row)
        new_rows.append(row)
    return {"results": new_rows}


async def _process_file(upload: UploadFile) -> dict:
    row = {"source_filename": upload.filename}

    if not upload.filename.lower().endswith(".pdf"):
        return {**row, "status": "error", "error_message": "Not a PDF file"}

    file_bytes = await upload.read()
    if not file_bytes:
        return {**row, "status": "error", "error_message": "Empty file"}

    try:
        text = extract_text(file_bytes)
    except Exception as exc:
        return {**row, "status": "error", "error_message": f"Could not read PDF: {exc}"}

    if not text:
        return {
            **row,
            "status": "no_text_found",
            "error_message": "No extractable text (likely a scanned image; OCR not implemented)",
        }

    try:
        fields = extract_invoice_fields(text)
    except Exception as exc:
        return {**row, "status": "error", "error_message": f"LLM extraction failed: {exc}"}

    try:
        record = InvoiceRecord(**fields)
    except ValidationError as exc:
        return {**row, "status": "error", "error_message": f"Invalid LLM output: {exc}"}

    return {**row, **record.model_dump(), "status": "ok"}


@app.post("/api/reset")
def reset():
    RESULTS.clear()
    return {"status": "ok"}


@app.get("/api/export.csv")
def export_csv():
    csv_text = rows_to_csv(RESULTS)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoice_export.csv"},
    )
