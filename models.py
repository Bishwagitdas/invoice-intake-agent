from typing import Optional, List
from pydantic import BaseModel, Field

class InvoiceLine(BaseModel):
    description: str
    quantity: Optional[int] = None
    unit: str
    unit_price: Optional[int] = None
    amount: int
    tax_code: str

class InvoiceData(BaseModel):
    partner_name: str
    partner_code: Optional[str] = None
    invoice_number: str
    issue_date: str
    due_date: str
    currency: str = "JPY"
    lines: List[InvoiceLine]
    subtotal: int
    tax_amount: int
    total_amount: int
    registration_number: Optional[str] = None

class ExtractionResult(BaseModel):
    invoice: InvoiceData
    confidence: float = Field(ge=0, le=1)
    warnings: List[str] = []
    evidence: List[str] = []
