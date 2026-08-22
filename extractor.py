import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import List

import pymupdf
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

        # Optional JSON mode.
        # Set LLM_JSON_MODE=true if the selected provider/model supports it.
        self.json_mode = (
            os.getenv("LLM_JSON_MODE", "false").lower()
            == "true"
        )

        # Number of LLM attempts for malformed responses.
        self.max_attempts = int(
            os.getenv("LLM_MAX_ATTEMPTS", "2")
        )

        # Maximum output tokens.
        self.max_tokens = int(
            os.getenv("LLM_MAX_TOKENS", "2500")
        )

    # ============================================================
    # PDF TEXT
    # ============================================================

    def _pdf_text(self, path: Path) -> str:

        doc = pymupdf.open(path)

        try:
            pages = []

            for page in doc:
                text = page.get_text("text").strip()

                if text:
                    pages.append(text)

            return "\n".join(pages)

        finally:
            doc.close()

    # ============================================================
    # PDF IMAGES
    # ============================================================

    def _pdf_images(self, path: Path) -> List[str]:

        doc = pymupdf.open(path)
        images = []

        try:
            # Only first 2 pages.
            # This prevents unnecessarily large requests.
            for page in doc[:2]:

                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(
                        0.65,
                        0.65
                    ),
                    alpha=False
                )

                image_bytes = pix.tobytes(
                    "jpeg",
                    jpg_quality=40
                )

                encoded = base64.b64encode(
                    image_bytes
                ).decode("ascii")

                images.append(
                    "data:image/jpeg;base64,"
                    + encoded
                )

        finally:
            doc.close()

        return images

    # ============================================================
    # IMAGE FILE
    # ============================================================

    def _image_data_url(self, path: Path) -> str:

        with Image.open(path) as img:

            img = img.convert("RGB")

            # Reduce large images.
            img.thumbnail(
                (1100, 1100)
            )

            buffer = io.BytesIO()

            img.save(
                buffer,
                format="JPEG",
                quality=60,
                optimize=True
            )

            encoded = base64.b64encode(
                buffer.getvalue()
            ).decode("ascii")

            return (
                "data:image/jpeg;base64,"
                + encoded
            )

    # ============================================================
    # FIND JSON OBJECT
    # ============================================================

    def _find_json_object(self, text: str) -> str:

        if not text:
            raise ValueError(
                "Empty response from LLM."
            )

        text = text.strip()

        # --------------------------------------------------------
        # Remove markdown fences
        # --------------------------------------------------------

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\s*```\s*$",
            "",
            text
        )

        text = text.strip()

        # --------------------------------------------------------
        # First try normal JSON decoding
        # --------------------------------------------------------

        try:
            json.loads(text)
            return text

        except json.JSONDecodeError:
            pass

        # --------------------------------------------------------
        # Find balanced JSON object.
        #
        # This handles:
        #
        # Here is the JSON:
        # { ... }
        #
        # --------------------------------------------------------

        start = text.find("{")

        if start == -1:
            raise ValueError(
                "LLM response does not contain JSON."
            )

        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):

            char = text[index]

            if in_string:

                if escaped:
                    escaped = False

                elif char == "\\":
                    escaped = True

                elif char == '"':
                    in_string = False

                continue

            if char == '"':
                in_string = True

            elif char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:

                    candidate = text[
                        start:index + 1
                    ]

                    try:
                        json.loads(candidate)
                        return candidate

                    except json.JSONDecodeError:
                        raise ValueError(
                            "LLM returned an incomplete or invalid JSON object."
                        )

        raise ValueError(
            "LLM response contains an incomplete JSON object."
        )

    # ============================================================
    # PARSE JSON
    # ============================================================

    def _parse_json(self, content: str) -> dict:

        json_text = self._find_json_object(
            content
        )

        try:
            data = json.loads(
                json_text
            )

        except json.JSONDecodeError as error:

            raise ValueError(
                f"Invalid JSON returned by LLM: {error}"
            ) from error

        if not isinstance(data, dict):

            raise ValueError(
                "LLM response is not a JSON object."
            )

        required = {
            "invoice",
            "confidence",
            "warnings",
            "evidence",
        }

        missing = (
            required
            - set(data.keys())
        )

        if missing:

            raise ValueError(
                "LLM response missing fields: "
                + ", ".join(
                    sorted(missing)
                )
            )

        if not isinstance(
            data["invoice"],
            dict
        ):

            raise ValueError(
                "'invoice' must be a JSON object."
            )

        return data

    # ============================================================
    # BUILD PROMPT
    # ============================================================

    def _build_prompt(self, retry=False) -> str:

        if retry:

            return """
Your previous answer was invalid.

Extract the invoice again.

IMPORTANT:

Return ONLY one complete JSON object.

DO NOT return:
- Markdown
- ```json
- explanations
- comments
- multiple JSON objects
- partial JSON
- text before or after JSON

The root object MUST contain exactly:

{
  "invoice": {},
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

The invoice MUST contain:

{
  "partner_name": "",
  "partner_code": null,
  "invoice_number": "",
  "issue_date": "",
  "due_date": "",
  "currency": "JPY",
  "lines": [],
  "subtotal": 0,
  "tax_amount": 0,
  "total_amount": 0,
  "registration_number": null
}

Every line MUST contain:

{
  "description": "",
  "quantity": null,
  "unit": null,
  "unit_price": null,
  "amount": 0,
  "tax_code": "T10"
}

LINE RULES:

- quantity = number or null
- unit = printed unit
- Examples: 個, 箱, 式, セット, 台, 件, 時間
- NEVER put Japanese units inside quantity
- If quantity is missing, use null
- If unit is printed, preserve it
- If unit_price is missing, use null
- amount must be the printed line amount

OTHER RULES:

- Preserve Japanese text.
- Do not invent information.
- Missing optional values = null.
- Dates = YYYY-MM-DD.
- Currency = JPY.
- 10% = T10.
- 8% = T08.
- Use printed subtotal.
- Use printed tax.
- Use printed total.
- Do not calculate missing values.
- confidence = number from 0 to 1.
- warnings = array.
- evidence = array.

Return JSON only.
"""

        return """
Extract the invoice from the supplied document.

Return EXACTLY ONE complete valid JSON object.

The root object MUST contain:

{
  "invoice": {},
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

The invoice MUST contain:

{
  "partner_name": "",
  "partner_code": null,
  "invoice_number": "",
  "issue_date": "",
  "due_date": "",
  "currency": "JPY",
  "lines": [],
  "subtotal": 0,
  "tax_amount": 0,
  "total_amount": 0,
  "registration_number": null
}

Each line MUST contain:

{
  "description": "",
  "quantity": null,
  "unit": null,
  "unit_price": null,
  "amount": 0,
  "tax_code": "T10"
}

LINE EXTRACTION RULES:

- quantity must be a number or null.
- unit must contain the printed unit.
- Preserve Japanese units exactly.
- Examples: 個, 箱, 式, セット, 台, 件, 時間.
- NEVER put a unit such as 式 into quantity.
- If the invoice shows "式", put "式" in unit.
- If quantity is missing, use null.
- If unit is printed but quantity is missing, preserve the unit.
- If unit_price is missing, use null.
- amount must be the printed line amount.

GENERAL RULES:

- Return JSON only.
- No Markdown.
- No explanations.
- No code fences.
- No multiple JSON objects.
- Preserve Japanese text.
- Do not invent information.
- Missing optional values = null.
- Dates must be YYYY-MM-DD.
- Currency must be JPY.
- 10% tax = T10.
- 8% tax = T08.
- Use printed subtotal, tax and total.
- Do not calculate missing values.
- confidence must be between 0 and 1.
- warnings must always be an array.
- evidence must always be an array.

IMPORTANT:
Finish the complete JSON response.
Do not stop in the middle of a string or object.
"""

    # ============================================================
    # BUILD REQUEST
    # ============================================================

    def _request(
        self,
        content,
        prompt
    ):

        messages = [
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

        kwargs = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

        # Optional provider JSON mode.
        if self.json_mode:

            kwargs["response_format"] = {
                "type": "json_object"
            }

        return self.client.chat.completions.create(
            **kwargs
        )

    # ============================================================
    # EXTRACT
    # ============================================================

    def extract(self, path: Path) -> ExtractionResult:

        suffix = path.suffix.lower()

        content = []

        # --------------------------------------------------------
        # PDF
        # --------------------------------------------------------

        if suffix == ".pdf":

            text = self._pdf_text(path)

            if text:

                # Keep text small to reduce TPM usage.
                content.append({
                    "type": "text",
                    "text": (
                        "Invoice text:\n"
                        + text[:3000]
                    )
                })

            images = self._pdf_images(
                path
            )

            for image in images:

                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image
                    }
                })

        # --------------------------------------------------------
        # IMAGE
        # --------------------------------------------------------

        elif suffix in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": self._image_data_url(
                        path
                    )
                }
            })

        else:

            raise ValueError(
                f"Unsupported file type: {path}"
            )

        # --------------------------------------------------------
        # Attempts
        # --------------------------------------------------------

        last_error = None

        for attempt in range(
            self.max_attempts
        ):

            prompt = self._build_prompt(
                retry=attempt > 0
            )

            try:

                response = self._request(
                    content,
                    prompt
                )

                if not response.choices:

                    raise ValueError(
                        "LLM returned no choices."
                    )

                raw = (
                    response
                    .choices[0]
                    .message
                    .content
                )

                if not raw:

                    raise ValueError(
                        "LLM returned an empty response."
                    )

                data = self._parse_json(
                    raw
                )

                return ExtractionResult.model_validate(
                    data
                )

            except Exception as error:

                last_error = error

                error_text = str(error)

                # ------------------------------------------------
                # Daily token limit
                # ------------------------------------------------

                if (
                    "tokens per day" in error_text.lower()
                    or "tpd" in error_text.lower()
                ):

                    raise RuntimeError(
                        "LLM daily token limit reached. "
                        "This invoice was not processed. "
                        "Try again after the provider quota resets "
                        "or switch LLM_MODEL."
                    ) from error

                # ------------------------------------------------
                # Request too large
                # ------------------------------------------------

                if (
                    "request too large" in error_text.lower()
                    or "tokens per minute" in error_text.lower()
                    or "tpm" in error_text.lower()
                    or "413" in error_text
                ):

                    if attempt + 1 < self.max_attempts:

                        # Wait before retry.
                        time.sleep(3)

                        continue

                # ------------------------------------------------
                # Temporary rate limit
                # ------------------------------------------------

                if (
                    "429" in error_text
                    or "too many requests"
                    in error_text.lower()
                ):

                    if attempt + 1 < self.max_attempts:

                        time.sleep(5)

                        continue

                # ------------------------------------------------
                # Invalid JSON
                # ------------------------------------------------

                if (
                    "invalid json"
                    in error_text.lower()
                    or "missing fields"
                    in error_text.lower()
                    or "does not contain json"
                    in error_text.lower()
                    or "incomplete json"
                    in error_text.lower()
                ):

                    if attempt + 1 < self.max_attempts:

                        time.sleep(1)

                        continue

                # Other error:
                # retry if attempts remain.
                if attempt + 1 < self.max_attempts:

                    time.sleep(1)

        raise RuntimeError(
            f"Invoice extraction failed: {last_error}"
        ) from last_error