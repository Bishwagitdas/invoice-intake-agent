import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from accounting_client import AccountingClient
from extractor import InvoiceExtractor
from verifier import verify


load_dotenv()

ROOT = Path(__file__).resolve().parent
INVOICE_DIR = ROOT / "invoices"
OUTPUT_DIR = ROOT / "outputs"


def partner_match(name, partners):
    name = (name or "").strip()

    # Exact match
    for partner in partners:
        if partner.get("name") == name:
            return partner, 1.0

    # Alias / partial match
    for partner in partners:
        aliases = partner.get("aliases", [])

        if (
            name in aliases
            or name in partner.get("name", "")
            or partner.get("name", "") in name
        ):
            return partner, 0.9

    return None, 0.0


def process(path, extractor, client, partners):
    print(f"\n=== {path.name} ===")

    result = extractor.extract(path)
    invoice = result.invoice

    # Supplier matching
    partner, match_conf = partner_match(
        invoice.partner_name,
        partners
    )

    if partner:
        invoice.partner_code = partner["partner_code"]
    else:
        result.warnings.append(
            "Supplier could not be matched to accounting partner master."
        )

    # Independent verification
    ok, errors, checks = verify(invoice)

    threshold = float(
        os.getenv("CONFIDENCE_THRESHOLD", "0.85")
    )

    review_required = (
        result.confidence < threshold
        or match_conf < 1.0
        or bool(result.warnings)
        or not ok
    )

    record = {
        "file": path.name,
        "extraction": result.model_dump(),
        "partner_match_confidence": match_conf,
        "verification": {
            "passed": ok,
            "errors": errors,
            "details": checks
        },
        "status": "REVIEW" if review_required else "READY",
        "registration": None
    }

    # Register only if fully validated
    if not review_required:
        payload = invoice.model_dump(
            exclude={
                "partner_name",
                "registration_number"
            }
        )

        status, response = client.register(payload)

        record["registration"] = {
            "http_status": status,
            "response": response
        }

        record["status"] = (
            "REGISTERED"
            if response.get("success")
            else "REGISTRATION_FAILED"
        )

    # Save JSON audit record
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = OUTPUT_DIR / f"{path.stem}.json"

    output_file.write_text(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        json.dumps(
            record,
            ensure_ascii=False,
            indent=2
        )
    )

    return record


def get_invoice_files():
    if not INVOICE_DIR.exists():
        return []

    return sorted(
        path
        for path in INVOICE_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower()
        in {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        }
    )


def main():
    extractor = InvoiceExtractor()
    client = AccountingClient()

    # Get accounting partners once
    partners = client.partners()

    # --------------------------------------------------
    # MODE 1:
    # python main.py invoice_01.pdf
    #
    # Process ONLY the specified invoice
    # --------------------------------------------------
    if len(sys.argv) > 1:

        filename = sys.argv[1]
        path = INVOICE_DIR / filename

        if not path.exists():
            print(
                f"Invoice not found: {path}"
            )
            return 1

        if path.suffix.lower() not in {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        }:
            print(
                f"Unsupported invoice type: {path.suffix}"
            )
            return 1

        try:
            process(
                path,
                extractor,
                client,
                partners
            )
            return 0

        except Exception as exc:
            print(
                f"{path.name}: FAILED - {exc}"
            )
            return 1

    # --------------------------------------------------
    # MODE 2:
    # python main.py
    #
    # Process ALL invoices
    # --------------------------------------------------
    files = get_invoice_files()

    if not files:
        print(
            "No invoices found in invoices/."
        )
        return 1

    print(
        f"Found {len(files)} invoice(s)."
    )

    results = []

    for path in files:

        try:
            result = process(
                path,
                extractor,
                client,
                partners
            )

            results.append(result)

        except Exception as exc:

            print(
                f"{path.name}: FAILED - {exc}"
            )

            results.append({
                "file": path.name,
                "status": "FAILED",
                "error": str(exc)
            })

    # Summary
    summary = {
        "total": len(results),
        "registered": sum(
            r.get("status") == "REGISTERED"
            for r in results
        ),
        "review": sum(
            r.get("status") == "REVIEW"
            for r in results
        ),
        "failed": sum(
            r.get("status")
            in {
                "FAILED",
                "REGISTRATION_FAILED"
            }
            for r in results
        )
    }

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    summary_file = (
        OUTPUT_DIR / "summary.json"
    )

    summary_file.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "\nSUMMARY:",
        summary
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())