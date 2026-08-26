import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import pymupdf
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

from models import ExtractionResult
from prompts import SYSTEM_PROMPT


# ============================================================
# PROJECT ROOT / ENV
# ============================================================

ROOT = Path(__file__).resolve().parent

load_dotenv(
    ROOT / ".env",
    override=True
)


class InvoiceExtractor:

    def __init__(self):

        # ========================================================
        # LLM CONFIGURATION
        # ========================================================

        api_key = os.getenv("LLM_API_KEY")

        if not api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set."
            )

        self.base_url = os.getenv(
            "LLM_BASE_URL",
            ""
        )

        self.model = os.getenv(
            "LLM_MODEL",
            ""
        )

        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url
        )

        # ========================================================
        # DEBUG
        # ========================================================

        self.debug = (
            os.getenv(
                "DEBUG",
                "false"
            ).lower()
            == "true"
        )

        # ========================================================
        # JSON MODE
        # ========================================================

        self.json_mode = (
            os.getenv(
                "LLM_JSON_MODE",
                "false"
            ).lower()
            == "true"
        )

        # ========================================================
        # RETRIES
        # ========================================================

        self.max_attempts = int(
            os.getenv(
                "LLM_MAX_ATTEMPTS",
                "2"
            )
        )

        # ========================================================
        # OUTPUT TOKENS
        # ========================================================

        self.max_tokens = int(
            os.getenv(
                "LLM_MAX_TOKENS",
                "1800"
            )
        )

        # ========================================================
        # PDF IMAGE SETTINGS
        # ========================================================

        self.image_scale = float(
            os.getenv(
                "LLM_IMAGE_SCALE",
                "0.40"
            )
        )

        self.image_quality = int(
            os.getenv(
                "LLM_IMAGE_QUALITY",
                "22"
            )
        )

        # ========================================================
        # PAGE TEXT
        # ========================================================

        self.max_page_text = int(
            os.getenv(
                "LLM_MAX_PAGE_TEXT",
                "1200"
            )
        )

        # ========================================================
        # DEBUG
        # ========================================================

        self._log(
            f"Model: {self.model}"
        )

        self._log(
            f"Max tokens: {self.max_tokens}"
        )

        self._log(
            f"Max attempts: {self.max_attempts}"
        )

        self._log(
            f"JSON mode: {self.json_mode}"
        )

    # ============================================================
    # LOGGING
    # ============================================================

    def _log(
        self,
        message: str
    ) -> None:

        if self.debug:
            print(
                f"[InvoiceExtractor] {message}"
            )

    # ============================================================
    # PDF TEXT
    # ============================================================

    def _pdf_page_text(
        self,
        page
    ) -> str:

        return page.get_text(
            "text"
        ).strip()

    # ============================================================
    # PDF IMAGE
    # ============================================================

    def _pdf_page_image(
        self,
        page,
        scale: Optional[float] = None,
        quality: Optional[int] = None
    ) -> str:

        scale = (
            scale
            if scale is not None
            else self.image_scale
        )

        quality = (
            quality
            if quality is not None
            else self.image_quality
        )

        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(
                scale,
                scale
            ),
            alpha=False
        )

        image_bytes = pix.tobytes(
            "jpeg",
            jpg_quality=quality
        )

        encoded = base64.b64encode(
            image_bytes
        ).decode("ascii")

        return (
            "data:image/jpeg;base64,"
            + encoded
        )

    # ============================================================
    # IMAGE FILE
    # ============================================================

    def _image_data_url(
        self,
        path: Path,
        size: int = 850,
        quality: int = 45
    ) -> str:

        with Image.open(path) as img:

            img = img.convert("RGB")

            img.thumbnail(
                (size, size)
            )

            buffer = io.BytesIO()

            img.save(
                buffer,
                format="JPEG",
                quality=quality,
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
    # JSON EXTRACTION
    # ============================================================

    def _find_json_object(
        self,
        text: str
    ) -> str:

        if not text:
            raise ValueError(
                "Empty response from LLM."
            )

        text = text.strip()

        # --------------------------------------------------------
        # Remove Qwen reasoning
        # --------------------------------------------------------

        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL
            | re.IGNORECASE
        ).strip()

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
        # Complete JSON
        # --------------------------------------------------------

        try:
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                return text

        except json.JSONDecodeError:
            pass

        # --------------------------------------------------------
        # Find first JSON object
        # --------------------------------------------------------

        start = text.find("{")

        if start == -1:
            raise ValueError(
                "LLM response does not contain JSON."
            )

        depth = 0
        in_string = False
        escaped = False

        for index in range(
            start,
            len(text)
        ):

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

                        parsed = json.loads(
                            candidate
                        )

                        if isinstance(
                            parsed,
                            dict
                        ):
                            return candidate

                    except json.JSONDecodeError:
                        pass

        raise ValueError(
            "LLM response contains incomplete JSON."
        )

    # ============================================================
    # PARSE JSON
    # ============================================================

    def _parse_json(
        self,
        content: str
    ) -> dict:

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

        if not isinstance(
            data,
            dict
        ):

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

        if not isinstance(
            data["warnings"],
            list
        ):

            raise ValueError(
                "'warnings' must be an array."
            )

        if not isinstance(
            data["evidence"],
            list
        ):

            raise ValueError(
                "'evidence' must be an array."
            )

        try:

            confidence = float(
                data["confidence"]
            )

        except (
            TypeError,
            ValueError
        ):

            raise ValueError(
                "'confidence' must be a number."
            )

        if not 0 <= confidence <= 1:

            raise ValueError(
                "'confidence' must be between 0 and 1."
            )

        data["confidence"] = confidence

        return data

    # ============================================================
    # PROMPT
    # ============================================================

    def _build_prompt(
        self,
        retry=False,
        emergency=False
    ) -> str:

        if emergency:

            return """
Extract this invoice page.

Return ONLY ONE JSON object.

{
  "invoice": {
    "partner_name": null,
    "partner_code": null,
    "invoice_number": null,
    "issue_date": null,
    "due_date": null,
    "currency": "JPY",
    "lines": [],
    "subtotal": null,
    "tax_amount": null,
    "total_amount": null,
    "registration_number": null
  },
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

Line:
{
  "description": "",
  "quantity": null,
  "unit": null,
  "unit_price": null,
  "amount": 0,
  "tax_code": "T10"
}

JSON only.
Preserve Japanese.
Do not invent.
Missing values = null.
quantity = number or null.
unit = printed unit.
10% = T10.
8% = T08.
Dates = YYYY-MM-DD.
Currency = JPY.
"""

        if retry:

            return """
Extract the invoice page.

Return ONLY ONE complete JSON object.
No Markdown.
No explanation.
No <think>.
No text before or after JSON.

Missing values must be null.
Preserve Japanese.
Do not invent information.

Use this structure:

{
  "invoice": {
    "partner_name": null,
    "partner_code": null,
    "invoice_number": null,
    "issue_date": null,
    "due_date": null,
    "currency": "JPY",
    "lines": [],
    "subtotal": null,
    "tax_amount": null,
    "total_amount": null,
    "registration_number": null
  },
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

Each line:
{
  "description": "",
  "quantity": null,
  "unit": null,
  "unit_price": null,
  "amount": 0,
  "tax_code": "T10"
}

Rules:
- quantity = number or null
- unit = printed unit
- Never put Japanese units in quantity
- Dates = YYYY-MM-DD
- Currency = JPY
- 10% = T10
- 8% = T08
- Use printed amounts
"""

        return """
Extract this invoice page.

Return EXACTLY ONE valid JSON object.

{
  "invoice": {
    "partner_name": null,
    "partner_code": null,
    "invoice_number": null,
    "issue_date": null,
    "due_date": null,
    "currency": "JPY",
    "lines": [],
    "subtotal": null,
    "tax_amount": null,
    "total_amount": null,
    "registration_number": null
  },
  "confidence": 0.0,
  "warnings": [],
  "evidence": []
}

Each line:
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
- No Markdown.
- No explanations.
- No <think>.
- Preserve Japanese.
- Do not invent.
- Missing values = null.
- Dates = YYYY-MM-DD.
- Currency = JPY.
- quantity = number or null.
- unit = printed unit or null.
- Never put Japanese units inside quantity.
- 10% = T10.
- 8% = T08.
- Use printed amounts.
- confidence = 0 to 1.
- warnings = array.
- evidence = array.
"""

    # ============================================================
    # REQUEST
    # ============================================================

    def _request(
        self,
        content,
        prompt,
        max_tokens: Optional[int] = None
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
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else self.max_tokens
            ),
            "messages": messages,
        }

        if self.json_mode:

            kwargs["response_format"] = {
                "type": "json_object"
            }

        return self.client.chat.completions.create(
            **kwargs
        )

    # ============================================================
    # ERROR HELPERS
    # ============================================================

    def _is_request_too_large(
        self,
        error_text: str
    ) -> bool:

        text = error_text.lower()

        return (
            "request too large" in text
            or "413" in text
        )

    # ============================================================
    # RATE LIMIT WAIT TIME
    # ============================================================

    def _get_retry_seconds(
        self,
        error_text: str
    ) -> float:

        # Example:
        # "Please try again in 4.1775s"

        match = re.search(
            r"try again in\s+([0-9.]+)\s*s",
            error_text,
            flags=re.IGNORECASE
        )

        if match:

            try:

                return float(
                    match.group(1)
                ) + 0.5

            except ValueError:
                pass

        # Safe fallback
        return 6.0

    # ============================================================
    # RATE LIMIT DETECTION
    # ============================================================

    def _is_rate_limit(
        self,
        error_text: str
    ) -> bool:

        text = error_text.lower()

        return (
            "rate limit" in text
            or "too many requests" in text
            or "429" in text
            or "tokens per minute" in text
        )

    # ============================================================
    # JSON ERROR DETECTION
    # ============================================================

    def _is_json_error(
        self,
        error_text: str
    ) -> bool:

        text = error_text.lower()

        json_errors = (
            "invalid json",
            "missing fields",
            "does not contain json",
            "incomplete json",
            "not a json object",
            "must be a json object",
            "must be an array",
            "must be a number",
            "confidence",
            "empty response",
        )

        return any(
            item in text
            for item in json_errors
        )

    # ============================================================
    # EXTRACT ONE PAGE
    # ============================================================

    def _extract_page(
        self,
        page,
        page_number: int
    ) -> dict:

        page_text = self._pdf_page_text(
            page
        )

        # ========================================================
        # PAYLOAD LEVELS
        #
        # IMPORTANT:
        # Each PDF page is sent separately.
        #
        # This means:
        #
        # 1 page  -> 1 page request
        # 2 pages -> 2 page requests
        # 3 pages -> 3 page requests
        # 10 pages -> 10 page requests
        #
        # Never send the complete PDF as one request.
        # ========================================================

        payloads = [
            {
                "scale": self.image_scale,
                "quality": self.image_quality,
                "text_limit": self.max_page_text,
                "max_tokens": self.max_tokens,
                "emergency": False,
            },
            {
                "scale": 0.30,
                "quality": 16,
                "text_limit": 500,
                "max_tokens": 1200,
                "emergency": True,
            },
            {
                "scale": 0.22,
                "quality": 12,
                "text_limit": 250,
                "max_tokens": 900,
                "emergency": True,
            },
            {
                "scale": 0.18,
                "quality": 10,
                "text_limit": 120,
                "max_tokens": 700,
                "emergency": True,
            },
        ]

        last_error = None

        for payload_index, settings in enumerate(
            payloads
        ):

            self._log(
                f"Page {page_number}: "
                f"payload "
                f"{payload_index + 1}/"
                f"{len(payloads)}"
            )

            image = self._pdf_page_image(
                page,
                scale=settings["scale"],
                quality=settings["quality"]
            )

            text = page_text[
                :settings["text_limit"]
            ]

            content = []

            if text:

                content.append({
                    "type": "text",
                    "text": (
                        "Invoice page text:\n"
                        + text
                    )
                })

            content.append({
                "type": "image_url",
                "image_url": {
                    "url": image
                }
            })

            for attempt in range(
                self.max_attempts
            ):

                try:

                    response = self._request(
                        content,
                        self._build_prompt(
                            retry=attempt > 0,
                            emergency=settings[
                                "emergency"
                            ]
                        ),
                        max_tokens=settings[
                            "max_tokens"
                        ]
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
                            "LLM returned empty response."
                        )

                    data = self._parse_json(
                        raw
                    )

                    self._log(
                        f"Page {page_number}: "
                        "extraction successful."
                    )

                    return data

                except Exception as error:

                    last_error = error

                    error_text = str(
                        error
                    )

                    # ============================================
                    # DAILY TOKEN LIMIT
                    # ============================================

                    if (
                        "tokens per day"
                        in error_text.lower()
                        or "tpd"
                        in error_text.lower()
                    ):

                        raise RuntimeError(
                            "LLM daily token limit reached."
                        ) from error

                    # ============================================
                    # REQUEST TOO LARGE
                    #
                    # 413 means the payload itself is too large.
                    # Immediately use smaller payload.
                    # ============================================

                    if self._is_request_too_large(
                        error_text
                    ):

                        self._log(
                            f"Page {page_number}: "
                            "request too large; "
                            "switching to smaller "
                            "payload."
                        )

                        break

                    # ============================================
                    # 429 / TPM
                    #
                    # Wait for the exact time Groq requests.
                    # ============================================

                    if self._is_rate_limit(
                        error_text
                    ):

                        wait_seconds = (
                            self._get_retry_seconds(
                                error_text
                            )
                        )

                        self._log(
                            f"Page {page_number}: "
                            f"rate limited; "
                            f"waiting "
                            f"{wait_seconds:.1f}s."
                        )

                        if (
                            attempt + 1
                            < self.max_attempts
                        ):

                            time.sleep(
                                wait_seconds
                            )

                            continue

                        # If retry attempts are exhausted,
                        # try smaller payload.
                        break

                    # ============================================
                    # INVALID JSON
                    # ============================================

                    if self._is_json_error(
                        error_text
                    ):

                        self._log(
                            f"Page {page_number}: "
                            "invalid response; "
                            "retrying."
                        )

                        if (
                            attempt + 1
                            < self.max_attempts
                        ):

                            time.sleep(1)

                            continue

                        break

                    # ============================================
                    # GENERIC RETRY
                    # ============================================

                    if (
                        attempt + 1
                        < self.max_attempts
                    ):

                        time.sleep(1)

        raise RuntimeError(
            f"Page {page_number} extraction failed: "
            f"{last_error}"
        ) from last_error

    # ============================================================
    # EXTRACT IMAGE
    # ============================================================

    def _extract_image(
        self,
        path: Path
    ) -> dict:

        # ========================================================
        # IMAGE PAYLOAD LEVELS
        #
        # Same fallback strategy as PDF pages.
        # ========================================================

        payloads = [
            {
                "size": 850,
                "quality": 45,
                "max_tokens": self.max_tokens,
                "emergency": False,
            },
            {
                "size": 650,
                "quality": 30,
                "max_tokens": 1200,
                "emergency": True,
            },
            {
                "size": 500,
                "quality": 22,
                "max_tokens": 900,
                "emergency": True,
            },
            {
                "size": 400,
                "quality": 18,
                "max_tokens": 700,
                "emergency": True,
            },
        ]

        last_error = None

        for payload_index, settings in enumerate(
            payloads
        ):

            self._log(
                f"Image payload "
                f"{payload_index + 1}/"
                f"{len(payloads)}"
            )

            image = self._image_data_url(
                path,
                size=settings["size"],
                quality=settings["quality"]
            )

            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image
                    }
                }
            ]

            for attempt in range(
                self.max_attempts
            ):

                try:

                    response = self._request(
                        content,
                        self._build_prompt(
                            retry=attempt > 0,
                            emergency=settings[
                                "emergency"
                            ]
                        ),
                        max_tokens=settings[
                            "max_tokens"
                        ]
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
                            "LLM returned empty response."
                        )

                    data = self._parse_json(
                        raw
                    )

                    self._log(
                        "Image extraction successful."
                    )

                    return data

                except Exception as error:

                    last_error = error

                    error_text = str(
                        error
                    )

                    # ============================================
                    # DAILY TOKEN LIMIT
                    # ============================================

                    if (
                        "tokens per day"
                        in error_text.lower()
                        or "tpd"
                        in error_text.lower()
                    ):

                        raise RuntimeError(
                            "LLM daily token limit reached."
                        ) from error

                    # ============================================
                    # REQUEST TOO LARGE
                    # ============================================

                    if self._is_request_too_large(
                        error_text
                    ):

                        self._log(
                            "Image request too large; "
                            "reducing payload."
                        )

                        break

                    # ============================================
                    # RATE LIMIT
                    # ============================================

                    if self._is_rate_limit(
                        error_text
                    ):

                        wait_seconds = (
                            self._get_retry_seconds(
                                error_text
                            )
                        )

                        self._log(
                            f"Image rate limited; "
                            f"waiting "
                            f"{wait_seconds:.1f}s."
                        )

                        if (
                            attempt + 1
                            < self.max_attempts
                        ):

                            time.sleep(
                                wait_seconds
                            )

                            continue

                        break

                    # ============================================
                    # JSON ERROR
                    # ============================================

                    if self._is_json_error(
                        error_text
                    ):

                        if (
                            attempt + 1
                            < self.max_attempts
                        ):

                            time.sleep(1)

                            continue

                        break

                    # ============================================
                    # GENERIC
                    # ============================================

                    if (
                        attempt + 1
                        < self.max_attempts
                    ):

                        time.sleep(1)

        raise RuntimeError(
            f"Image extraction failed: "
            f"{last_error}"
        ) from last_error

    # ============================================================
    # MERGE PAGE RESULTS
    # ============================================================

    def _merge_results(
        self,
        results: List[dict]
    ) -> dict:

        if not results:

            raise ValueError(
                "No page results."
            )

        merged = json.loads(
            json.dumps(
                results[0],
                ensure_ascii=False
            )
        )

        invoice = merged.setdefault(
            "invoice",
            {}
        )

        invoice.setdefault(
            "lines",
            []
        )

        # ========================================================
        # MERGE ALL PAGES
        # ========================================================

        for result in results[1:]:

            page_invoice = result.get(
                "invoice",
                {}
            )

            # ----------------------------------------------------
            # LINES
            # ----------------------------------------------------

            lines = page_invoice.get(
                "lines",
                []
            )

            if lines:

                invoice["lines"].extend(
                    lines
                )

            # ----------------------------------------------------
            # HEADER
            # ----------------------------------------------------

            header_fields = [
                "partner_name",
                "partner_code",
                "invoice_number",
                "issue_date",
                "due_date",
                "currency",
                "registration_number",
            ]

            for field in header_fields:

                current = invoice.get(
                    field
                )

                incoming = page_invoice.get(
                    field
                )

                if (
                    current in (None, "")
                    and incoming not in (
                        None,
                        ""
                    )
                ):

                    invoice[field] = incoming

            # ----------------------------------------------------
            # TOTALS
            # ----------------------------------------------------

            for field in [
                "subtotal",
                "tax_amount",
                "total_amount",
            ]:

                incoming = page_invoice.get(
                    field
                )

                if incoming not in (
                    None,
                    0
                ):

                    invoice[field] = incoming

            # ----------------------------------------------------
            # WARNINGS
            # ----------------------------------------------------

            page_warnings = result.get(
                "warnings",
                []
            )

            merged.setdefault(
                "warnings",
                []
            )

            merged["warnings"].extend(
                page_warnings
            )

            # ----------------------------------------------------
            # EVIDENCE
            # ----------------------------------------------------

            page_evidence = result.get(
                "evidence",
                []
            )

            merged.setdefault(
                "evidence",
                []
            )

            merged["evidence"].extend(
                page_evidence
            )

        # ========================================================
        # CONFIDENCE
        # ========================================================

        confidences = [
            float(
                result.get(
                    "confidence",
                    0
                )
            )
            for result in results
        ]

        merged["confidence"] = min(
            confidences
        )

        # ========================================================
        # UNIQUE WARNINGS
        # ========================================================

        merged["warnings"] = list(
            dict.fromkeys(
                merged.get(
                    "warnings",
                    []
                )
            )
        )

        # ========================================================
        # UNIQUE EVIDENCE
        # ========================================================

        merged["evidence"] = list(
            dict.fromkeys(
                merged.get(
                    "evidence",
                    []
                )
            )
        )

        return merged

    # ============================================================
    # EXTRACT
    # ============================================================

    def extract(
        self,
        path: Path
    ) -> ExtractionResult:

        suffix = path.suffix.lower()

        # ========================================================
        # PDF
        # ========================================================

        if suffix == ".pdf":

            doc = pymupdf.open(
                path
            )

            try:

                page_count = len(
                    doc
                )

                self._log(
                    f"Processing {path.name} "
                    f"({page_count} page(s))"
                )

                page_results = []

                # ------------------------------------------------
                # EVERY PAGE IS PROCESSED SEPARATELY
                # ------------------------------------------------

                for page_number, page in enumerate(
                    doc,
                    start=1
                ):

                    self._log(
                        f"Processing page "
                        f"{page_number}/"
                        f"{page_count}"
                    )

                    result = self._extract_page(
                        page,
                        page_number
                    )

                    page_results.append(
                        result
                    )

                data = self._merge_results(
                    page_results
                )

            finally:

                doc.close()

        # ========================================================
        # IMAGE
        # ========================================================

        elif suffix in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:

            self._log(
                f"Processing image: "
                f"{path.name}"
            )

            data = self._extract_image(
                path
            )

        # ========================================================
        # UNSUPPORTED
        # ========================================================

        else:

            raise ValueError(
                f"Unsupported file type: {path}"
            )

        # ========================================================
        # FINAL PYDANTIC VALIDATION
        # ========================================================

        return ExtractionResult.model_validate(
            data
        )