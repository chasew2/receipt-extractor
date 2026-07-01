"""
extractor.py — Receipt / invoice data extraction using the Claude API.

Sends a single receipt image or PDF to Claude and gets back structured fields
(vendor, date, total, tax, category, ...). We hand Claude the schema as a
*tool* and force it to call that tool, so the response is always valid JSON in
exactly the shape we expect — no brittle string parsing.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from typing import Optional

import anthropic

# Sonnet 4.6 is a solid accuracy/cost balance for vision extraction.
# For high-volume batches at lower cost, switch to "claude-haiku-4-5".
# For faded receipts or messy handwriting, "claude-opus-4-8" is the most accurate.
DEFAULT_MODEL = "claude-sonnet-4-6"

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# The fields we pull from every receipt, in the order we want them in the sheet.
FIELD_ORDER = [
    "vendor",
    "date",
    "category",
    "subtotal",
    "tax",
    "total",
    "currency",
    "payment_method",
    "line_item_summary",
    "confidence",
]

# Defining the schema as a tool forces Claude to return valid, structured JSON.
RECEIPT_TOOL = {
    "name": "record_receipt",
    "description": (
        "Record the structured data extracted from a single receipt or invoice. "
        "Use null for any field that is missing or not legible. Amounts must be "
        "plain numbers with no currency symbols or thousands separators."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor": {
                "type": ["string", "null"],
                "description": "Merchant or business name.",
            },
            "date": {
                "type": ["string", "null"],
                "description": "Transaction date, normalized to YYYY-MM-DD.",
            },
            "currency": {
                "type": ["string", "null"],
                "description": "ISO currency code, e.g. USD, CAD, EUR. Infer if not printed.",
            },
            "subtotal": {
                "type": ["number", "null"],
                "description": "Pre-tax subtotal.",
            },
            "tax": {
                "type": ["number", "null"],
                "description": "Total tax amount.",
            },
            "total": {
                "type": ["number", "null"],
                "description": "Grand total actually paid.",
            },
            "payment_method": {
                "type": ["string", "null"],
                "description": "e.g. Visa ****1234, Cash, Amex, Interac.",
            },
            "category": {
                "type": ["string", "null"],
                "description": (
                    "Best-guess expense category, e.g. Meals, Travel, "
                    "Office Supplies, Software, Fuel, Utilities."
                ),
            },
            "line_item_summary": {
                "type": ["string", "null"],
                "description": "A few words summarizing what was purchased.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Your confidence that the extracted fields are correct.",
            },
        },
        "required": ["vendor", "date", "total", "category", "confidence"],
    },
}

SYSTEM_PROMPT = (
    "You are a meticulous bookkeeping assistant. You read a single receipt or "
    "invoice image and extract its key fields accurately. If a value is missing "
    "or illegible, return null instead of guessing. Normalize every date to "
    "YYYY-MM-DD. Strip currency symbols and separators from amounts so they are "
    "plain numbers. Choose the most specific sensible expense category. Set "
    "confidence to 'low' whenever the image is blurry, cropped, or ambiguous."
)


def _guess_media_type(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename)
    if mt in SUPPORTED_IMAGE_TYPES or mt == "application/pdf":
        return mt
    # Fall back to PNG for unknown image extensions.
    return "image/png"


def _build_content_block(file_bytes: bytes, media_type: str) -> dict:
    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": b64},
    }


@dataclass
class ExtractionResult:
    """One receipt's worth of extracted data (or an error)."""

    source_file: str
    data: dict
    error: Optional[str] = None

    def as_row(self) -> dict:
        row = {"source_file": self.source_file}
        for field in FIELD_ORDER:
            row[field] = self.data.get(field)
        row["error"] = self.error
        return row


def extract_receipt(
    client: anthropic.Anthropic,
    file_bytes: bytes,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> ExtractionResult:
    """Extract structured data from a single receipt image or PDF."""
    media_type = _guess_media_type(filename)
    content_block = _build_content_block(file_bytes, media_type)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[RECEIPT_TOOL],
            tool_choice={"type": "tool", "name": "record_receipt"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        content_block,
                        {"type": "text", "text": "Extract the fields from this receipt."},
                    ],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 — surface any API/network error to the UI
        return ExtractionResult(source_file=filename, data={}, error=str(exc))

    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_receipt":
            return ExtractionResult(source_file=filename, data=dict(block.input))

    return ExtractionResult(
        source_file=filename,
        data={},
        error="Model did not return structured data.",
    )
