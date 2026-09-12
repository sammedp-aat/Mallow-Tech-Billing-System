"""
Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- Product Schemas ----------
class ProductBase(BaseModel):
    product_id: str = Field(..., max_length=50, description="Unique product code e.g. P101")
    name: str = Field(..., max_length=150)
    available_stocks: int = Field(..., ge=0)
    price_per_unit: float = Field(..., ge=0)
    tax_percentage: float = Field(..., ge=0, le=100)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    available_stocks: Optional[int] = Field(None, ge=0)
    price_per_unit: Optional[float] = Field(None, ge=0)
    tax_percentage: Optional[float] = Field(None, ge=0, le=100)


class ProductResponse(ProductBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ---------- Bill Schemas ----------
class BillItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)


class BillCreate(BaseModel):
    customer_email: EmailStr
    items: List[BillItemCreate]
    cash_paid: float = Field(..., ge=0)
    available_denominations: Dict[int, int] = Field(
        default_factory=lambda: {500: 20, 50: 20, 20: 20, 10: 20, 5: 20, 2: 20, 1: 20}
    )


class BillItemResponse(BaseModel):
    id: int
    product_id: str
    product_name: str
    unit_price: float
    quantity: int
    purchase_price: float
    tax_percentage: float
    tax_payable: float
    total_price: float

    model_config = ConfigDict(from_attributes=True)


class BillResponse(BaseModel):
    id: int
    bill_number: str
    customer_email: str
    total_without_tax: float
    total_tax_payable: float
    net_price: float
    rounded_down_net_price: float
    cash_paid: float
    balance_payable: float
    denominations_returned: Optional[str] = None
    created_at: datetime
    items: List[BillItemResponse] = []

    model_config = ConfigDict(from_attributes=True)
