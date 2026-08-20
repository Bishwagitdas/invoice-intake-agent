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
    n = (name or "").strip()
    exact = [p for p in partners if p["name"] == n]
    if exact:
        return exact[0], 1.0
    for p in partners:
        if n in p.get("aliases", []) or n in p.get("name", "") or p.get("name", "") in n:
            return p, 0.9
    return None, 0.0

def process(path, extractor, client, partners):
    print(f"\n=== {path.name} ===")
    result = extractor.extract(path)
    invoice = result.invoice

    partner, match_conf = partner_match(invoice.partner_name, partners)
    if partner:
        invoice.partner_code = partner["partner_code"]
    else:
        result.warnings.append("Supplier could not be matched to accounting partner master.")

    ok, errors, checks = verify(invoice)
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
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
        "verification": {"passed": ok, "errors": errors, "details": checks},
        "status": "REVIEW" if review_required else "READY",
    }

    if not review_required:
        payload = invoice.model_dump(exclude={"partner_name", "registration_number"})
        status, response = client.register(payload)
        record["registration"] = {"http_status": status, "response": response}
        record["status"] = "REGISTERED" if response.get("success") else "REGISTRATION_FAILED"
    else:
        record["registration"] = None

    out = OUTPUT_DIR / f"{path.stem}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return record

def main():
    extractor = InvoiceExtractor()
    client = AccountingClient()
    partners = client.partners()

    files = sorted(
        p for p in INVOICE_DIR.iterdir()
        if p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
    )
    if not files:
        print("No invoices found in invoices/.")
        return 1

    results = []
    for path in files:
        try:
            results.append(process(path, extractor, client, partners))
        except Exception as exc:
            print(f"{path.name}: FAILED - {exc}")
            results.append({"file": path.name, "status": "FAILED", "error": str(exc)})

    summary = {
        "total": len(results),
        "registered": sum(r.get("status") == "REGISTERED" for r in results),
        "review": sum(r.get("status") == "REVIEW" for r in results),
        "failed": sum(r.get("status") in {"FAILED", "REGISTRATION_FAILED"} for r in results),
    }
    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nSUMMARY:", summary)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
