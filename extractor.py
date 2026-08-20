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
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
        self.client = OpenAI(api_key=key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def _pdf_text(self, path: Path) -> str:
        doc = fitz.open(path)
        return "\n".join(page.get_text("text") for page in doc).strip()

    def _pdf_images(self, path: Path) -> List[str]:
        doc = fitz.open(path)
        out = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            out.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode())
        return out

    def _image_data_url(self, path: Path) -> str:
        with Image.open(path) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def extract(self, path: Path) -> ExtractionResult:
        suffix = path.suffix.lower()
        content = []
        if suffix == ".pdf":
            text = self._pdf_text(path)
            if text:
                content.append({"type": "text", "text": "PDF text layer:\n" + text})
            # Always provide rendered pages too; this catches table/layout information.
            for img in self._pdf_images(path):
                content.append({"type": "image_url", "image_url": {"url": img}})
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            content.append({"type": "image_url", "image_url": {"url": self._image_data_url(path)}})
        else:
            raise ValueError(f"Unsupported file type: {path}")

        schema = ExtractionResult.model_json_schema()
        user_text = """Extract this invoice. Use the JSON schema exactly.
Do not calculate values that are not supported by the document.
For tax, map 10% -> T10 and 8% -> T08.
Confidence is your confidence in the overall extraction, not OCR confidence.

JSON schema:
""" + json.dumps(schema, ensure_ascii=False)

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [{"type": "text", "text": user_text}] + content},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        return ExtractionResult.model_validate(data)
