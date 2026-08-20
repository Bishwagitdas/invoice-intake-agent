import json
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"

st.set_page_config(page_title="Invoice Review", layout="wide")
st.title("Invoice Intake — Human Review")

files = sorted(OUT.glob("*.json"))
files = [p for p in files if p.name != "summary.json"]

if not files:
    st.info("Run `python main.py` first. Reviewable extraction results will appear here.")
    st.stop()

for path in files:
    data = json.loads(path.read_text(encoding="utf-8"))
    with st.expander(f"{data['file']} — {data.get('status')}"):
        ext = data.get("extraction", {})
        inv = ext.get("invoice", {})
        st.write("**Supplier:**", inv.get("partner_name"))
        st.write("**Invoice number:**", inv.get("invoice_number"))
        st.write("**Issue date:**", inv.get("issue_date"))
        st.write("**Due date:**", inv.get("due_date"))
        st.write("**Subtotal / Tax / Total:**",
                 inv.get("subtotal"), inv.get("tax_amount"), inv.get("total_amount"))
        st.write("**Confidence:**", ext.get("confidence"))
        st.write("**Warnings:**", ext.get("warnings"))
        st.write("**Verification:**", data.get("verification"))
        st.json(inv)
