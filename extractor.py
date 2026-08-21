import base64
import io
import json
import os
from pathlib import Path
from typing import List

import fitz
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

from models import ExtractionResult
from prompts import SYSTEM_PROMPT

load_dotenv()


class InvoiceExtractor:
    def __init__(self):
        api_key = os.getenv("LLM_API_KEY")

        if not api_key:
            raise RuntimeError("LLM_API_KEY is not set.")

        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv(
                "LLM_BASE_URL",
                "https://api.openai.com/v1"
            ),
        )

        self.model = os.getenv(
            "LLM_MODEL",
            "gpt-4o-mini"
        )

    def _pdf_text(self, path: Path) -> str:
        doc = fitz.open(path)

        try:
            return "\n".join(
                page.get_text("text")
                for page in doc
            ).strip()
        finally:
            doc.close()

    def _pdf_images(self, path: Path) -> List[str]:
        doc = fitz.open(path)
        images = []

        try:
            for page in doc:
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(0.8, 0.8),
                    alpha=False
                )

                images.append(
                    "data:image/jpeg;base64,"
                    + base64.b64encode(
                        pix.tobytes("jpeg", jpg_quality=50)
                    ).decode()
                )

        finally:
            doc.close()

        return images

    def _image_data_url(self, path: Path) -> str:
        with Image.open(path) as img:
            buffer = io.BytesIO()

            img.thumbnail((1400, 1400))

            img.convert("RGB").save(
                buffer,
                format="JPEG",
                quality=70
            )

            return (
                "data:image/jpeg;base64,"
                + base64.b64encode(
                    buffer.getvalue()
                ).decode()
            )

    def _parse_json(self, content: str) -> dict:
        if not content:
            raise ValueError("Empty response from LLM.")

        content = content.strip()

        if "```" in content:
            content = content.replace("```json", "")
            content = content.replace("```", "")
            content = content.strip()

        start = content.find("{")

        if start == -1:
            raise ValueError(
                "LLM response does not contain JSON."
            )

        decoder = json.JSONDecoder()

        try:
            data, _ = decoder.raw_decode(
                content[start:]
            )
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON returned by LLM: {error}"
            ) from error

        if not isinstance(data, dict):
            raise ValueError(
                "LLM response is not a JSON object."
            )

        if "invoice" not in data:
            raise ValueError(
                "LLM response does not contain 'invoice'."
            )

        if "confidence" not in data:
            raise ValueError(
                "LLM response does not contain 'confidence'."
            )

        return data

    def extract(self, path: Path) -> ExtractionResult:
        suffix = path.suffix.lower()
        content = []

        if suffix == ".pdf":
            text = self._pdf_text(path)

            if text:
                content.append({
                    "type": "text",
                    "text": (
                        "Invoice text:\n"
                        + text[:5000]
                    )
                })

            images = self._pdf_images(path)

            for image in images:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image
                    }
                })

        elif suffix in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        }:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": self._image_data_url(path)
                }
            })

        else:
            raise ValueError(
                f"Unsupported file type: {path}"
            )

        prompt = """
Extract this invoice.

Return ONLY ONE valid JSON object.

Required fields:

{
  "invoice": {
    "partner_name": "",
    "partner_code": null,
    "invoice_number": "",
    "issue_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "currency": "JPY",
    "lines": [],
    "subtotal": 0,
    "tax_amount": 0,
    "total_amount": 0,
    "registration_number": null
  },
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

Line format:

{
  "description": "",
  "quantity": null,
  "unit": null,
  "unit_price": null,
  "amount": 0,
  "tax_code": "T10"
}

Rules:
- JSON only.
- No markdown.
- No explanations.
- Include all required fields.
- Preserve Japanese text.
- Do not invent information.
- Use null for missing optional values.
- Dates must be YYYY-MM-DD.
- Currency is JPY.
- 10% = T10.
- 8% = T08.
- Use printed line amounts.
- Confidence must be between 0 and 1.
- Add warnings when information is unclear.
"""

        last_error = None

        for attempt in range(2):

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    messages=[
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt
                                }
                            ] + content
                        }
                    ]
                )

                raw = response.choices[0].message.content

                data = self._parse_json(raw)

                return ExtractionResult.model_validate(data)

            except Exception as error:

                last_error = error

                if attempt == 0:
                    prompt = """
Return the invoice again.

IMPORTANT:
Return exactly ONE JSON object.

The root object MUST contain:

- invoice
- confidence
- warnings
- evidence

Do not return a line item as the root object.
Do not return markdown.
Do not return explanations.
Do not return multiple JSON objects.

Return JSON only.
"""

        raise last_error