# Submission

Name: Bishwagit Das
Submission date (YYYY-MM-DD): 2026-08-26
Hours actually spent: Approximately 10 hours
Repository / how to run it: See README.md; start the accounting API with `python accounting_api.py`, then run `python main.py`.

## 1. Understanding the request

The client wants to reduce manual invoice data entry while continuing to use the existing accounting system. The problem is not simply OCR or reading text from invoices. The actual problem is creating a controlled intake pipeline that can extract invoice information from different layouts, verify the extracted values, match the supplier to the accounting master, and only then register the invoice.

I therefore designed the solution around the following workflow:

`Invoice -> AI extraction -> structured validation -> supplier matching -> deterministic verification -> registration or review`

The system supports text-based PDFs, scanned PDFs, and scanned image invoices. Since the invoices are Japanese and have different layouts, I used a vision-capable LLM so that the model can use both document text and visual information.

Most importantly, I treated LLM output as untrusted input. Before registration, the extracted data is independently checked for date validity, tax codes, subtotal, tax, total, currency, and supplier information.

The goal is to automate straightforward invoices while preventing uncertain or mathematically inconsistent AI output from being directly posted to the accounting system.

## 2. What you would have asked the client

| What you wanted to ask | The assumption you made | Why |
|---|---|---|
| Which LLM/OCR service is approved? | Use a configurable OpenAI-compatible vision LLM API. | The assignment allows us to choose the model, and keeping the provider configurable avoids tightly coupling the application to one service. |
| What confidence level is acceptable for auto-posting? | Use `0.85` as a conservative extraction-confidence threshold together with deterministic validation. | Accounting data is high impact, so uncertain invoices should go to review rather than being automatically registered. |
| What should happen to uncertain invoices? | Route them to human review and do not register them automatically. | A manual review is safer than creating an incorrect accounting record. |
| Are duplicate invoice numbers possible across suppliers? | Follow the accounting API behavior: duplicates are identified by supplier/partner code plus invoice number. | This matches the supplied accounting system specification. |
| How are supplier names normalized? | Match the extracted supplier against the supplied partner master and aliases, then use the corresponding partner code. | The accounting API only accepts suppliers that exist in its partner master. |
| Should printed invoice arithmetic be trusted? | No. Recalculate subtotal, tax, and total from the extracted line items before registration. | The accounting API itself recalculates these values, so the application should validate them first. |
| What should happen if the LLM provider reaches a token or rate limit? | Retry where appropriate and reduce the request payload; if the provider's daily limit is reached, fail the invoice safely instead of producing incomplete data. | Provider limits are operational failures and should be visible rather than hidden. |

## 3. Scoping decisions

### What you built

- Multi-format invoice ingestion for PDF and image files.
- PDF text extraction using PyMuPDF when a text layer is available.
- PDF page rendering for scanned/image-only PDFs.
- Image processing for JPG, JPEG, PNG, and WebP invoices.
- Vision-based LLM extraction for Japanese invoice content.
- Structured JSON extraction using a fixed schema.
- Pydantic validation of the extracted structure.
- Supplier/partner matching against the accounting system's partner master.
- Independent arithmetic, date, currency, and tax verification.
- Confidence and warning information in the extraction result.
- Accounting API integration.
- Duplicate and API validation error handling.
- JSON output/audit information.
- Retry handling for malformed LLM responses and rate-limit/request-size failures.
- Smaller fallback payloads when an LLM request is too large.
- Optional Streamlit review interface.
- Command-line processing through `main.py`.

### What you left out, and why

The assignment is intentionally scoped around approximately eight hours, so I prioritized correctness, verification, and accounting-system integration over production infrastructure.

I did not build:

1. **A production message queue**

   A queue would be useful for asynchronous processing and retry management, but it was not necessary to demonstrate the core invoice-intake workflow.

2. **A persistent production database**

   The supplied accounting API stores registrations in memory. I kept the implementation focused on the provided environment rather than introducing a separate production database.

3. **Enterprise authentication and authorization**

   The supplied accounting API already defines authentication through its API key. A complete user-management system was outside the scope of this assignment.

4. **An OCR ensemble or multiple-model pipeline**

   I used a vision-capable LLM to keep the implementation focused. A production solution could benchmark several OCR/vision approaches and select the best one based on field-level accuracy and cost.

5. **Enterprise monitoring and alerting**

   The application includes logging and explicit failure handling, but a complete monitoring stack was outside the time scope.

6. **A complete persistent human approval workflow**

   I included the review boundary and an optional review interface, but a production-quality reviewer workflow with persistent approval history and resubmission would require additional implementation.

The main priority was to make sure that AI output is not automatically trusted and that invalid accounting data is blocked before registration.

## 4. Design and technology choices

### End-to-end flow

```text
PDF / JPG / PNG
       |
       v
Document ingestion
       |
       +--> PDF text layer -> extracted text
       |
       +--> PDF/image rendering -> invoice image
       |
       v
Vision-capable LLM
       |
       v
Structured JSON
       |
       v
Pydantic validation
       |
       v
Supplier matching
       |
       v
Deterministic verification
       |
       +-----------------------+
       |                       |
       v                       v
   Valid/Trusted          Uncertain/Invalid
       |                       |
       v                       v
Accounting API             Human Review
       |
       v
Registered Invoice
```

Python was chosen because the assignment explicitly prefers Python or TypeScript and the supplied accounting API is written in Python.

PyMuPDF is used for PDF text extraction and page rendering. For image-based invoices, the document is passed to the vision-capable LLM as an image.

I chose a configurable OpenAI-compatible vision LLM API rather than tightly coupling the application to one provider. The model, API endpoint, and API key are configured through `.env`.

I decided against relying only on traditional OCR because these invoices have different layouts and may contain tables, Japanese text, scanned content, and handwritten or visually important information. The vision model can use the document layout together with extracted text.

I also decided against allowing the LLM to directly register invoices. The LLM is responsible for extraction; deterministic application logic is responsible for verification and the final registration decision.

## 5. How you used AI, and how you checked it

### What you delegated to AI

The LLM receives the invoice page as visual input and, for PDFs with a text layer, a limited amount of extracted page text as additional context.

I instructed the model to return a fixed JSON structure containing:

- Supplier name
- Partner code when available
- Invoice number
- Issue date
- Due date
- Currency
- Line descriptions
- Quantity
- Unit
- Unit price
- Line amount
- Tax code
- Subtotal
- Tax amount
- Total amount
- Registration number
- Confidence
- Warnings
- Evidence

The prompt explicitly instructs the model to preserve Japanese text, use YYYY-MM-DD dates, use JPY, distinguish T10 and T08, avoid inventing missing values, and return JSON only.

### How you verified the output

I do not treat the model's output as authoritative.

The extracted result is first validated against the Pydantic schema. Then deterministic verification checks:

- Date format and date ordering.
- JPY currency requirement.
- Supported tax codes.
- Supplier/partner matching.
- Subtotal against the sum of line amounts.
- Tax separately by tax code.
- Total against subtotal plus calculated tax.
- Accounting API constraints before registration.

The accounting API also independently recalculates amounts, providing a second validation boundary.

If the extraction is incomplete, uncertain, inconsistent, or the provider fails, the invoice is not silently registered.

### A case where the AI got it wrong

During testing, malformed/incomplete LLM responses and provider token-limit failures occurred. These cases demonstrated an important production behavior: an invoice should not be registered simply because the model returned something.

For example, when the LLM response could not be parsed into the required JSON structure, the extractor retried with a stricter prompt. When the request was too large, the implementation reduced the image/text payload and retried.

For provider daily-token-limit failures, the invoice is reported as FAILED rather than generating or registering potentially incomplete data.

This reinforces the design principle that the LLM is an extraction component, not the final source of truth.

## 6. Integrating with the accounting system

The implementation follows the supplied accounting API specification and does not change its behavior.

The application handles:

- X-API-Key authentication.
- Partner master lookup.
- Partner code validation.
- Supplier matching using the supplied partner information.
- T10 and T08 tax codes.
- JPY-only integer amounts.
- YYYY-MM-DD dates.
- Due-date validation.
- Duplicate invoice handling.
- Subtotal, tax, and total verification.
- Accounting API registration errors.

| Invoice | Result | How you handled it |
|---|---|---|
| Successfully extracted and verified invoices | REGISTERED | Sent to the accounting API only after validation passed. |
| Low-confidence or uncertain invoices | REVIEW | Kept out of automatic registration for human checking. |
| Invalid arithmetic/date/tax/supplier data | REVIEW / FAILED | Blocked before registration and recorded as a validation failure. |
| LLM JSON/parsing failure | RETRY / FAILED | Retried with a stricter prompt; if unsuccessful, the invoice was not registered. |
| LLM request too large | RETRY | Reduced image quality/text payload and retried with a smaller request. |
| LLM daily token limit reached | FAILED | Stopped safely and reported the provider-limit failure instead of producing unreliable output. |
| Duplicate invoice | REJECTED | The accounting API's duplicate protection prevents a second registration for the same partner and invoice number. |

The design intentionally favors false negatives over incorrect accounting registrations. An invoice that requires manual review is preferable to an incorrect automated posting.

## 7. Cost, limits, and risk in production

### Cost per invoice

The main variable cost is the vision/LLM request. It depends on:

- Model/provider pricing.
- Number of invoice pages.
- Image resolution and compression.
- Input tokens.
- Output tokens.
- Number of retries.

The model and provider are configurable, so production cost should be measured using a representative invoice set before selecting the final provider.

### Monthly cost at 1,000 invoices per month

A simple estimate is:

`Monthly LLM cost = average cost per invoice × 1,000`

For example, if benchmarking shows an average cost of $0.01 per invoice, the LLM portion would be approximately $10/month for 1,000 invoices, excluding compute, storage, monitoring, and human review.

The actual figure should be measured against real invoice sizes rather than assuming a fixed cost.

### Processing time per invoice

For a single-page invoice, processing is primarily affected by document rendering and the LLM API request. Multi-page invoices require additional page-level extraction requests.

A production implementation could process independent invoices concurrently using a queue and worker architecture.

### Where this breaks first

The most likely failure points are:

- Very poor-quality scans.
- Handwritten or ambiguous fields.
- Unusual invoice layouts.
- Complex multi-page tables.
- Suppliers that cannot be confidently matched to the partner master.
- Invoices with internally inconsistent printed arithmetic.
- LLM provider rate/token limits.
- Unexpected model output or malformed JSON.

These cases should be treated as review/failure conditions rather than silently automated.

### How you would find out if something was registered incorrectly

A production system should maintain an audit trail containing:

- Original invoice/document.
- Extracted structured JSON.
- Verification results.
- Confidence and warnings.
- Model/provider information.
- Processing timestamp.
- Accounting API request/response.
- Accounting record ID.

Periodic reconciliation should compare source invoices against registered accounting records. Duplicate detection and idempotency should also be enforced around the registration step.

## 8. What you would do with another 8 hours

**Build a stronger human review and correction workflow**

Add a side-by-side invoice image and extracted fields, allowing a reviewer to correct values and explicitly approve/resubmit an invoice. This is the highest priority because difficult invoices are the natural boundary of AI automation.

**Add persistent audit/job storage and idempotent registration**

Store processing state, retries, review decisions, and accounting API responses in a database. Add idempotency around registration so that network retries cannot accidentally create duplicate accounting records.

**Benchmark all 12 invoices at field level**

Measure accuracy for supplier, invoice number, dates, line items, tax codes, subtotal, tax, and total. Use the results to tune the model, prompt, image resolution, and fallback strategy based on actual errors rather than assumptions.
