import io

import pdfplumber


def extract_text(file_bytes: bytes) -> str:
    """Extract all text from a PDF's pages, concatenated with newlines.

    Returns an empty string if the PDF has no extractable text layer
    (e.g. a scanned image with no OCR applied).
    """
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()
