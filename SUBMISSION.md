# Submission

- Name: Bishwagit Das
- Submission date (YYYY-MM-DD): 2026-08-21
- Hours actually spent: 8
- Repository / how to run it: See README.md; `python accounting_api.py` then `python main.py`

## 1. Understanding the request

The client wants to reduce manual invoice data entry while keeping the existing accounting system. The actual problem I set out to solve is not simply OCR; it is a controlled intake pipeline that can extract invoice data from different layouts, verify the extracted values, match the supplier to the accounting master, and only then register the invoice.

## 2. What you would have asked the client

| What you wanted to ask | The assumption you made | Why |
|---|---|---|
| Which LLM/OCR service is approved? | Use a configurable LLM vision API. | The assignment requires us to choose and justify a model. |
| What confidence level is acceptable for auto-posting? | 0.85 overall extraction confidence plus deterministic validation. | A conservative threshold is safer for accounting data. |
| What should happen to uncertain invoices? | Route them to human review and do not register them. | A wrong accounting entry is more costly than a manual review. |
| Are duplicate invoices possible across suppliers? | The accounting API defines duplicates by supplier + invoice number. | We follow the existing system's behavior. |
| How are supplier names normalized? | Use exact name first, then supplied aliases/controlled matching. | The API provides a finite partner master. |

## 3. Scoping decisions

**What you built**

- Multi-format invoice ingestion.
- LLM-based extraction with Japanese text and vision input.
- Supplier master matching.
- Independent arithmetic/date/tax verification.
- Confidence and warning-based human-review boundary.
- Accounting API integration.
- JSON audit output.
- Optional Streamlit review screen.
- Single-command processing after the API is started.

**What you left out, and why**

I did not build a production queue, persistent database, full authentication system, advanced OCR ensemble, or enterprise monitoring. The assignment is intentionally scoped to about eight hours and contains only 12 invoices. I prioritized correctness, verification, integration, and explainability over infrastructure.

## 4. Design and technology choices

Flow:

`Invoice PDF/Image -> text extraction/rendering -> LLM vision extraction -> Pydantic validation -> supplier matching -> deterministic verification -> human review OR accounting API -> JSON audit record`

Python was chosen because the assignment explicitly prefers Python or TypeScript and the supplied accounting API is Python.

PyMuPDF is used for PDFs. An OpenAI-compatible vision model is used for extraction because the invoices are Japanese and may be scans with different layouts. The model is configurable through `.env`.

I decided against treating OCR text as sufficient by itself because table structure, handwritten/unclear fields, and scanned invoices can make plain text extraction unreliable.

## 5. How you used AI, and how you checked it

**What you delegated to AI**

The LLM receives invoice text when a PDF has a text layer and rendered page images for visual context. It extracts invoice number, dates, supplier, line items, tax codes and amounts into a fixed schema.

**How you verified the output**

I independently recalculate subtotal, tax by tax code, total, and date ordering. I also match the supplier against the accounting API master. Low confidence, warnings, non-exact supplier matches, or failed arithmetic checks force human review.

**A case where the AI got it wrong**

A useful production test is to deliberately perturb an extracted amount or tax value. The deterministic verification layer detects the mismatch and prevents registration. This demonstrates why the model output is treated as an input to validation, not as the source of truth.

## 6. Integrating with the accounting system

The implementation uses the supplied API key and endpoints without changing the API specification.

| Invoice | Result | How you handled it |
|---|---|---|
| Each input invoice | REGISTERED / REVIEW / FAILED | Validated invoices are posted; uncertain or invalid invoices remain in JSON review records. |

Important API constraints handled include JPY-only integer amounts, YYYY-MM-DD dates, T10/T08 tax codes, partner-code validation, duplicate invoice handling, and recalculated amounts.

## 7. Cost, limits, and risk in production

- **Cost per invoice:** Primarily the vision/LLM token cost; exact cost depends on model, image resolution, and number of pages. The provider/model is configurable so production pricing can be benchmarked with real documents.
- **Monthly cost at 1,000 invoices per month:** Approximately 1,000 times the measured per-invoice model cost, plus storage/compute. A pilot should measure the actual average before committing to a fixed estimate.
- **Processing time per invoice:** Typically dominated by the LLM request and document rendering; a queue would allow parallel processing.
- **Where this breaks first:** Very poor scans, handwriting, unusual multi-page tables, supplier names outside the master, and invoices whose printed arithmetic is internally inconsistent.
- **How you would find out if something was registered incorrectly:** Keep the original document, extracted JSON, verification results, model metadata, and accounting API response as an audit trail; add periodic reconciliation between source invoices and registered accounting records.

## 8. What you would do with another 8 hours

1. Build a stronger review/edit workflow with side-by-side invoice image and extracted fields, then allow a reviewer to approve/resubmit.
2. Add a persistent job/audit database, retries, and idempotency around API registration.
3. Benchmark extraction accuracy across all 12 invoices and tune prompts/model/image resolution based on field-level errors.
