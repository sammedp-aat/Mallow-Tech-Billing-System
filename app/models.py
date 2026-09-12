"""
SQLAlchemy ORM models for Billing System.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    available_stocks = Column(Integer, nullable=False, default=0)
    price_per_unit = Column(Float, nullable=False)
    tax_percentage = Column(Float, nullable=False)

    def __repr__(self):
        return f"<Product {self.product_id} - {self.name}>"


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    bill_number = Column(String(50), unique=True, index=True, nullable=False)
    customer_email = Column(String(150), nullable=False, index=True)
    total_without_tax = Column(Float, nullable=False)
    total_tax_payable = Column(Float, nullable=False)
    net_price = Column(Float, nullable=False)
    rounded_down_net_price = Column(Float, nullable=False)
    cash_paid = Column(Float, nullable=False)
    balance_payable = Column(Float, nullable=False)
    denominations_returned = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Bill {self.bill_number}>"


class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(50), nullable=False)
    product_name = Column(String(150), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    purchase_price = Column(Float, nullable=False)  # unit_price * quantity
    tax_percentage = Column(Float, nullable=False)
    tax_payable = Column(Float, nullable=False)  # purchase_price * tax/100
    total_price = Column(Float, nullable=False)  # purchase_price + tax_payable

    bill = relationship("Bill", back_populates="items")

    def __repr__(self):
        return f"<BillItem {self.product_id} x{self.quantity}>"
