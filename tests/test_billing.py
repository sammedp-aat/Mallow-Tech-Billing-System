"""
Unit Tests for Billing System
Covers per-item calculations, aggregates, denomination algorithm, insufficient stock
Run: pytest -v
"""
import math
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Product
from app.services.billing_service import (
    calculate_item,
    calculate_bill_totals,
    calculate_denominations,
    create_bill,
)

# ---------- Test fixtures ----------
@pytest.fixture
def db():
    # In-memory SQLite for isolated tests
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed some test products
    p1 = Product(product_id="P101", name="Test Milk", available_stocks=50, price_per_unit=60.0, tax_percentage=5.0)
    p2 = Product(product_id="P102", name="Bread", available_stocks=40, price_per_unit=45.0, tax_percentage=5.0)
    p3 = Product(product_id="P103", name="Coffee", available_stocks=5, price_per_unit=350.0, tax_percentage=12.0)
    session.add_all([p1, p2, p3])
    session.commit()
    yield session
    session.close()


# ---------- Per-item calculations ----------
def test_calculate_item_basic():
    result = calculate_item(quantity=2, unit_price=60.0, tax_percentage=5.0)
    assert result["purchase_price"] == 120.0
    assert result["tax_payable"] == 6.0  # 120 * 5%
    assert result["total_price"] == 126.0


def test_calculate_item_with_decimal_tax():
    result = calculate_item(quantity=1, unit_price=350.0, tax_percentage=12.0)
    assert result["purchase_price"] == 350.0
    assert result["tax_payable"] == 42.0
    assert result["total_price"] == 392.0


def test_calculate_item_zero_tax():
    result = calculate_item(quantity=3, unit_price=100.0, tax_percentage=0.0)
    assert result["purchase_price"] == 300.0
    assert result["tax_payable"] == 0.0
    assert result["total_price"] == 300.0


def test_calculate_item_high_tax():
    result = calculate_item(quantity=2, unit_price=150.0, tax_percentage=18.0)
    assert result["purchase_price"] == 300.0
    assert result["tax_payable"] == 54.0
    assert result["total_price"] == 354.0


# ---------- Bill aggregates ----------
def test_bill_aggregate_single_item():
    items = [calculate_item(2, 60.0, 5.0)]  # 126 total
    totals = calculate_bill_totals(items)
    assert totals["total_without_tax"] == 120.0
    assert totals["total_tax_payable"] == 6.0
    assert totals["net_price"] == 126.0
    assert totals["rounded_down_net_price"] == 126.0


def test_bill_aggregate_multiple_items():
    items = [
        calculate_item(2, 60.0, 5.0),   # 126
        calculate_item(1, 45.0, 5.0),   # 47.25
        calculate_item(1, 350.0, 12.0), # 392
    ]
    totals = calculate_bill_totals(items)
    # Without tax: 120 +45 +350 = 515
    # Tax: 6 +2.25 +42 = 50.25
    # Net: 565.25 -> floor 565
    assert totals["total_without_tax"] == 515.0
    assert totals["total_tax_payable"] == 50.25
    assert totals["net_price"] == 565.25
    assert totals["rounded_down_net_price"] == 565.0


def test_floor_rounding():
    items = [calculate_item(1, 99.99, 10.0)]  # 99.99 + 9.999 = 109.989
    totals = calculate_bill_totals(items)
    assert totals["net_price"] == 109.99  # rounded to 2 decimals: 109.99
    assert totals["rounded_down_net_price"] == math.floor(109.99)


def test_balance_calculation():
    items = [calculate_item(1, 100.0, 5.0)]  # 105
    totals = calculate_bill_totals(items)
    cash_paid = 200
    balance = cash_paid - totals["rounded_down_net_price"]
    assert balance == 95.0


# ---------- Denomination algorithm ----------
def test_denomination_exact_change():
    balance = 93
    available = {500: 20, 50: 20, 20: 20, 10: 20, 5: 20, 2: 20, 1: 20}
    result, remaining, sufficient = calculate_denominations(balance, available)
    assert remaining == 0
    assert sufficient is True
    # 93 = 50*1 + 20*2 + 2*1 +1*1 => greedy
    assert result[50] == 1
    assert result[20] == 2
    assert result[10] == 0
    assert result[5] == 0
    assert result[2] == 1
    assert result[1] == 1
    # Verify sum
    total = sum(k * v for k, v in result.items())
    assert total == 93


def test_denomination_greedy_500():
    balance = 743
    available = {500: 20, 50: 20, 20: 20, 10: 20, 5: 20, 2: 20, 1: 20}
    result, remaining, sufficient = calculate_denominations(balance, available)
    assert sufficient is True
    assert result[500] == 1  # 500
    # remaining 243 => 50*4=200 (43 left) => 20*2=40 (3 left) => 2*1=2 (1 left) => 1*1=1
    assert result[50] == 4
    assert result[20] == 2
    assert result[2] == 1
    assert result[1] == 1
    assert sum(k*v for k,v in result.items()) == 743


def test_denomination_insufficient():
    balance = 100
    # Shop has no small denominations
    available = {500: 0, 50: 1, 20: 0, 10: 0, 5: 0, 2: 0, 1: 0}
    result, remaining, sufficient = calculate_denominations(balance, available)
    assert sufficient is False
    assert remaining == 50  # 100 - 50 = 50 remaining
    assert result[50] == 1
    assert result[500] == 0


def test_denomination_zero_balance():
    result, remaining, sufficient = calculate_denominations(0, {500:5, 50:5, 20:5, 10:5, 5:5, 2:5, 1:5})
    assert remaining == 0
    assert sufficient is True
    assert all(v == 0 for v in result.values())


def test_denomination_limited_stock():
    balance = 100
    available = {500:0, 50:1, 20:1, 10:5, 5:0, 2:0, 1:5}
    result, remaining, sufficient = calculate_denominations(balance, available)
    # Greedy: 50*1=50 (50 left), 20*1=20 (30 left), 10*3=30 -> success? Let's see: 10 has 5 avail, so 10*3 =30
    # So 50+20+30=100 sufficient
    assert sufficient is True
    assert result[50] == 1
    assert result[20] == 1
    assert result[10] == 3


def test_denomination_balance_large():
    balance = 1783
    available = {500:10, 50:10, 20:10, 10:10, 5:10, 2:10, 1:10}
    result, remaining, sufficient = calculate_denominations(balance, available)
    assert sufficient is True
    assert result[500] == 3  # 1500 (283 left)
    assert result[50] == 5   # 250 (33 left)
    assert result[20] == 1   # 20 (13 left)
    assert result[10] == 1   # 10 (3 left)
    assert result[2] == 1    # 2 (1 left)
    assert result[1] == 1    # 1 (0)
    assert sum(k*v for k,v in result.items()) == 1783


# ---------- Inventory & Transaction ----------
def test_insufficient_stock_raises(db):
    from fastapi import HTTPException
    # P103 has only 5 stock, try 10
    with pytest.raises(HTTPException) as exc:
        create_bill(
            db=db,
            customer_email="test@example.com",
            items_input=[{"product_id": "P103", "quantity": 10}],
            cash_paid=5000,
            available_denominations={500:20, 50:20, 20:20, 10:20, 5:20, 2:20, 1:20},
        )
    assert exc.value.status_code == 400
    assert "Insufficient stock" in exc.value.detail


def test_nonexistent_product_raises(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create_bill(
            db=db,
            customer_email="test@example.com",
            items_input=[{"product_id": "P999", "quantity": 1}],
            cash_paid=1000,
            available_denominations={500:20, 50:20, 20:20, 10:20, 5:20, 2:20, 1:20},
        )
    assert exc.value.status_code == 404


def test_insufficient_cash_raises(db):
    from fastapi import HTTPException
    # P101: 60 + 3 tax = 63 floor 63, cash 50 insufficient
    with pytest.raises(HTTPException) as exc:
        create_bill(
            db=db,
            customer_email="test@example.com",
            items_input=[{"product_id": "P101", "quantity": 1}],
            cash_paid=10,
            available_denominations={500:20, 50:20, 20:20, 10:20, 5:20, 2:20, 1:20},
        )
    assert exc.value.status_code == 400
    assert "Insufficient cash" in exc.value.detail


def test_successful_bill_creation_and_stock_decrement(db):
    initial_stock = db.query(Product).filter(Product.product_id == "P101").first().available_stocks
    bill = create_bill(
        db=db,
        customer_email="buyer@example.com",
        items_input=[{"product_id": "P101", "quantity": 2}],
        cash_paid=200,
        available_denominations={500:20, 50:20, 20:20, 10:20, 5:20, 2:20, 1:20},
    )
    assert bill.bill_number.startswith("BILL-")
    assert bill.total_without_tax == 120.0
    assert bill.total_tax_payable == 6.0
    assert bill.net_price == 126.0
    assert bill.rounded_down_net_price == 126.0
    assert bill.balance_payable == 74.0
    assert len(bill.items) == 1
    # Stock decremented
    new_stock = db.query(Product).filter(Product.product_id == "P101").first().available_stocks
    assert new_stock == initial_stock - 2


def test_bill_with_multiple_products(db):
    bill = create_bill(
        db=db,
        customer_email="multi@example.com",
        items_input=[
            {"product_id": "P101", "quantity": 1},
            {"product_id": "P102", "quantity": 2},
        ],
        cash_paid=500,
        available_denominations={500:5, 50:5, 20:5, 10:5, 5:5, 2:5, 1:5},
    )
    # P101: 60*1=60 +3=63, P102:45*2=90+4.5=94.5 => without=150 tax=7.5 net=157.5 floor 157 balance 343
    assert bill.total_without_tax == 150.0
    assert bill.total_tax_payable == 7.5
    assert bill.net_price == 157.5
    assert bill.rounded_down_net_price == 157.0
    assert bill.balance_payable == 343.0
    assert len(bill.items) == 2
