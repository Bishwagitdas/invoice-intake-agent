# AI Invoice Intake Agent

An AI-powered invoice intake pipeline for extracting, validating, reviewing, and registering Japanese invoices into an accounting system.

## Features

* Supports PDF, JPG, and PNG invoices
* Extracts Japanese invoice data using an LLM vision model
* Structured extraction with Pydantic validation
* Supplier/partner master matching
* Independent subtotal, tax, total, and date validation
* Confidence-based human review
* Duplicate invoice handling
* Accounting API integration
* JSON audit records
* Optional Streamlit review interface

## Project Flow

```text
Invoice
   ↓
PDF/Image Processing
   ↓
LLM Vision Extraction
   ↓
Pydantic Validation
   ↓
Supplier Matching
   ↓
Deterministic Verification
   ↓
 ┌───────────────┐
 │               │
Valid         Uncertain/Error
 │               │
 ↓               ↓
Register      Human Review
 │
 ↓
JSON Audit Record
```

## Requirements

* Python 3.11+
* OpenAI-compatible API key
* Internet connection for LLM API access

> Python 3.14 may work, but Python 3.11–3.13 is recommended for best package compatibility.

## 1. Clone the Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd invoice_intake_agent
```

## 2. Create Virtual Environment

### Windows Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
```

### Windows CMD

```cmd
python -m venv .venv
.venv\Scripts\activate
```

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=your_vision_model
ACCOUNTING_API_URL=http://127.0.0.1:8000
ACCOUNTING_API_KEY=your_accounting_api_key
```

Do not commit `.env` to Git.

## 5. Start the Accounting API

Open **Terminal 1**:

```bash
python accounting_api.py
```

Keep this terminal running.

## 6. Run Invoice Processing

Open **Terminal 2**:

```bash
python main.py
```

The application will:

1. Read the invoice files
2. Extract invoice information
3. Validate the structured data
4. Match the supplier
5. Recalculate amounts and taxes
6. Decide between registration and human review
7. Register valid invoices through the accounting API
8. Save processing/audit results as JSON

## 7. Optional Review UI

To launch the Streamlit review interface:

```bash
streamlit run review_app.py
```

The review interface can be used to inspect extracted invoice data, warnings, validation results, and review decisions.

## Supported Invoice Data

The extraction pipeline handles:

* Invoice number
* Invoice date
* Due date
* Supplier name
* Supplier/partner code
* Line items
* Quantity
* Unit price
* Tax code
* Tax amount
* Subtotal
* Total amount

Japanese invoice layouts and scanned/image-based documents are supported through vision-based extraction.

## Validation & Safety

The LLM output is **not treated as the source of truth**.

Before registration, the system independently checks:

* Required fields
* Date format and ordering
* Supplier/partner matching
* Subtotal calculations
* Tax calculations
* Total amount
* JPY integer amounts
* Supported tax codes
* Duplicate invoice conditions
* Extraction confidence

Invoices with failed validation, low confidence, warnings, or uncertain supplier matching are routed for review instead of being automatically registered.

## Human Review Rule

An invoice is eligible for automatic registration only when the extraction and deterministic validation checks pass.

Default extraction confidence threshold:

```text
0.85
```

Anything uncertain is kept in the review/audit output rather than being blindly posted.

## Accounting API

The integration follows the supplied accounting API specification.

Important constraints include:

* JPY amounts represented as integers
* `YYYY-MM-DD` date format
* Supported tax codes such as `T10` and `T08`
* Partner/supplier validation
* Duplicate invoice handling
* Server-side amount recalculation

## Output

Processing results are stored as JSON audit information.

Typical results:

```text
REGISTERED
REVIEW
FAILED
```

The audit information is intended to preserve:

* Original invoice reference
* Extracted fields
* Validation results
* Warnings
* Confidence information
* Supplier matching result
* Registration result
* Accounting API response

## Project Structure

```text
invoice_intake_agent/
│
├── invoices/              # Input invoices
├── outputs/               # Processing/audit results
├── main.py                # Main invoice processing pipeline
├── accounting_api.py      # Accounting API
├── review_app.py          # Streamlit review interface
├── requirements.txt       # Python dependencies
├── .env                   # Local configuration
├── .env.example           # Environment template
└── README.md              # Documentation
```

## AI Approach

The system uses the LLM for document understanding and structured extraction, while deterministic Python validation is responsible for accounting correctness.

This separation reduces the risk of incorrect AI-generated accounting entries.

## Scope

The implementation focuses on the core invoice-intake workflow within the assignment time constraint.

Not included:

* Production message queues
* Enterprise authentication
* Persistent production database
* Advanced OCR ensemble
* Full monitoring/alerting infrastructure

These can be added for production deployment.

## Production Improvements

With additional development time, the next priorities would be:

1. Side-by-side invoice image and editable review workflow
2. Persistent audit/job database
3. Retry and idempotency mechanisms
4. Field-level extraction accuracy benchmarking
5. Model and prompt optimization
6. Production monitoring and reconciliation

### Quick Start

```bash
git clone <YOUR_REPOSITORY_URL>
cd invoice_intake_agent

python -m venv .venv
source .venv/Scripts/activate

pip install -r requirements.txt
```

Configure `.env`, then:

**Terminal 1**

```bash
python accounting_api.py
```

**Terminal 2**

```bash
python main.py
```

**Optional UI**

```bash
streamlit run review_app.py
```
