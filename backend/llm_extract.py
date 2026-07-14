import os
import time

import anthropic

MODEL = "claude-sonnet-5"

EXTRACTION_TOOL = {
    "name": "record_invoice_data",
    "description": "Record structured data extracted from a utility invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {
                "type": ["string", "null"],
                "description": "Name of the utility provider issuing the invoice.",
            },
            "invoice_date": {
                "type": ["string", "null"],
                "description": "Date the invoice was issued, as ISO 8601 (YYYY-MM-DD). "
                "Null if not present or genuinely ambiguous.",
            },
            "service_address": {
                "type": ["string", "null"],
                "description": "Address where the utility service was rendered.",
            },
            "utility_type": {
                "type": ["string", "null"],
                "enum": ["electricity", "gas", "water", "other", None],
                "description": "Type of utility this invoice is for.",
            },
            "usage_amount": {
                "type": ["number", "null"],
                "description": "Numeric quantity of utility consumed in the billing period.",
            },
            "usage_unit": {
                "type": ["string", "null"],
                "description": "Unit for usage_amount, e.g. kWh, therms, m3, gallons.",
            },
            "billing_period_start": {
                "type": ["string", "null"],
                "description": "Start of the billing cycle, as ISO 8601 (YYYY-MM-DD).",
            },
            "billing_period_end": {
                "type": ["string", "null"],
                "description": "End of the billing cycle, as ISO 8601 (YYYY-MM-DD).",
            },
            "detected_language": {
                "type": ["string", "null"],
                "description": "Primary language of the source document, as an English word (e.g. 'English', 'French').",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Your overall confidence that the extracted fields are correct and "
                "complete, given how clear and unambiguous the source text was.",
            },
        },
        "required": ["confidence"],
    },
}

SYSTEM_PROMPT = """You are a utility invoice data extraction system. You will be given raw \
text extracted from a utility bill PDF (electricity, gas, or water), which may be in any \
language and any layout.

Call the record_invoice_data tool exactly once with the extracted fields. Rules:
- Always normalize dates to ISO 8601 (YYYY-MM-DD), regardless of the source format or language.
- Always normalize utility_type to one of: electricity, gas, water, other.
- Use null for any field that is missing, unclear, or not actually present in the text \
(e.g. a blank template with placeholder text like "mm/dd/yyyy" is NOT a real date -- use null).
- Never invent or guess a value. It is better to return null than a fabricated value.
- usage_amount must be the numeric consumption figure only (no currency amounts, no units).
- Set confidence honestly based on how much of the required data was clearly present."""


def extract_invoice_fields(invoice_text: str, max_retries: int = 1) -> dict:
    """Call Claude with a forced tool-use schema to extract structured invoice fields.

    Retries once with a short backoff on transient API errors. Raises the
    underlying exception if all attempts fail, letting the caller decide how
    to surface the failure for that specific file.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    attempt = 0
    while True:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "record_invoice_data"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Invoice text:\n\n{invoice_text}",
                    }
                ],
            )
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            if attempt >= max_retries:
                raise
            attempt += 1
            time.sleep(1.5 * attempt)

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_invoice_data":
            return block.input

    raise ValueError("Claude did not return a tool_use block")
