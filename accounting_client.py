import os
import requests
from dotenv import load_dotenv

load_dotenv()

class AccountingClient:
    def __init__(self):
        self.base_url = os.getenv("ACCOUNTING_API_URL", "http://localhost:8080").rstrip("/")
        self.headers = {
            "X-API-Key": os.getenv("ACCOUNTING_API_KEY", "demo-key-1234"),
            "Content-Type": "application/json",
        }

    def partners(self):
        r = requests.get(self.base_url + "/partners", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()["data"]["partners"]

    def tax_codes(self):
        r = requests.get(self.base_url + "/tax-codes", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()["data"]["tax_codes"]

    def register(self, payload):
        r = requests.post(self.base_url + "/invoices", headers=self.headers, json=payload, timeout=15)
        return r.status_code, r.json()
