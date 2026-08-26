from typing import Optional, List

from pydantic import BaseModel, Field


class InvoiceLine(BaseModel):

    description: str

    quantity: Optional[float] = None

    unit: Optional[str] = None

    unit_price: Optional[float] = None

    amount: float

    tax_code: str


class InvoiceData(BaseModel):

    partner_name: Optional[str] = None

    partner_code: Optional[str] = None

    invoice_number: Optional[str] = None

    issue_date: Optional[str] = None

    due_date: Optional[str] = None

    currency: str = "JPY"

    lines: List[InvoiceLine] = Field(
        default_factory=list
    )

    subtotal: Optional[float] = None

    tax_amount: Optional[float] = None

    total_amount: Optional[float] = None

    registration_number: Optional[str] = None


class ExtractionResult(BaseModel):

    invoice: InvoiceData

    confidence: float = Field(
        ge=0,
        le=1
    )

    warnings: List[str] = Field(
        default_factory=list
    )

    evidence: List[str] = Field(
        default_factory=list
    )