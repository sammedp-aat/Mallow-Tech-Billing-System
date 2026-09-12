"""
Billing Service - core business logic for calculations, denominations, and bill creation.
Production-grade with atomic transactions and clear error handling.
"""
import math
import json
import secrets
from datetime import datetime
from typing import Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Product, Bill, BillItem

# Canonical denomination order (high to low) - shop provides these
DENOMINATIONS = [500, 50, 20, 10, 5, 2, 1]


# ---------- Per-item calculations ----------
def calculate_item(quantity: int, unit_price: float, tax_percentage: float) -> dict:
    """
    Calculate per-item purchase price, tax payable and total.
    Returns dict with purchase_price, tax_payable, total_price.
    """
    purchase_price = unit_price * quantity
    tax_payable = purchase_price * (tax_percentage / 100.0)
    total_price = purchase_price + tax_payable
    return {
        "purchase_price": round(purchase_price, 2),
        "tax_payable": round(tax_payable, 2),
        "total_price": round(total_price, 2),
    }


def calculate_bill_totals(items: List[dict]) -> dict:
    """
    Aggregate totals for a list of items.
    Each item dict must have purchase_price and tax_payable.
    Returns total_without_tax, total_tax_payable, net_price, rounded_down_net_price.
    """
    total_without_tax = sum(i["purchase_price"] for i in items)
    total_tax_payable = sum(i["tax_payable"] for i in items)
    net_price = total_without_tax + total_tax_payable
    rounded_down = math.floor(net_price)
    return {
        "total_without_tax": round(total_without_tax, 2),
        "total_tax_payable": round(total_tax_payable, 2),
        "net_price": round(net_price, 2),
        "rounded_down_net_price": float(rounded_down),
    }


def calculate_denominations(balance: int, available: Dict[int, int]) -> Tuple[Dict[int, int], int, bool]:
    """
    Greedy change-making algorithm.

    Args:
        balance: integer amount of change to return (rounded down balance)
        available: dict {denomination: count_available}

    Returns:
        (denominations_to_return dict, remaining_balance int, is_sufficient bool)
        is_sufficient True if remaining == 0
    """
    if balance < 0:
        raise ValueError("Balance cannot be negative for denomination calculation")

    remaining = int(balance)
    result: Dict[int, int] = {}

    for denom in DENOMINATIONS:
        avail = int(available.get(denom, 0))
        if remaining <= 0:
            result[denom] = 0
            continue
        needed = remaining // denom
        to_give = min(needed, avail)
        result[denom] = to_give
        remaining -= to_give * denom

    is_sufficient = remaining == 0
    return result, remaining, is_sufficient


def generate_bill_number() -> str:
    """Generate unique bill number: BILL-YYYYMMDD-<hex>"""
    date_str = datetime.utcnow().strftime("%Y%m%d")
    rand_hex = secrets.token_hex(4).upper()  # 8 hex chars
    return f"BILL-{date_str}-{rand_hex}"


def create_bill(
    db: Session,
    customer_email: str,
    items_input: List[dict],
    cash_paid: float,
    available_denominations: Dict[int, int],
) -> Bill:
    """
    Atomic bill creation with inventory validation.

    items_input: list of {"product_id": str, "quantity": int}
    available_denominations: {500: int, 50:int, ...}
    cash_paid: float

    Raises HTTPException 400/404 on validation failures.
    Returns created Bill ORM object.
    """
    if not items_input:
        raise HTTPException(status_code=400, detail="At least one product is required.")

    if cash_paid is None or cash_paid < 0:
        raise HTTPException(status_code=400, detail="Cash paid must be non-negative.")

    # Normalize denominations keys to int
    normalized_denoms: Dict[int, int] = {}
    for k, v in (available_denominations or {}).items():
        try:
            ik = int(k)
            iv = int(v)
            normalized_denoms[ik] = iv
        except Exception:
            continue
    # Ensure all denominations present
    for d in DENOMINATIONS:
        normalized_denoms.setdefault(d, 0)

    # Validate products and compute per-item
    computed_items = []
    products_map: Dict[str, Product] = {}

    for entry in items_input:
        pid = str(entry.get("product_id", "")).strip()
        qty = entry.get("quantity")

        if not pid:
            raise HTTPException(status_code=400, detail="Product ID is required.")
        try:
            qty = int(qty)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid quantity for product {pid}")

        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"Quantity must be > 0 for {pid}")

        product = db.query(Product).filter(Product.product_id == pid).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {pid} not found.")

        if product.available_stocks < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {pid} ({product.name}). Available: {product.available_stocks}, Requested: {qty}",
            )

        calc = calculate_item(qty, product.price_per_unit, product.tax_percentage)
        computed_items.append(
            {
                "product": product,
                "product_id": product.product_id,
                "product_name": product.name,
                "unit_price": product.price_per_unit,
                "quantity": qty,
                "tax_percentage": product.tax_percentage,
                **calc,
            }
        )
        products_map[pid] = product

    # Aggregate totals
    totals = calculate_bill_totals(computed_items)
    rounded = totals["rounded_down_net_price"]

    # Validate cash sufficient for rounded price? Allow balance negative? No, require cash >= rounded
    # Business rule: balance = cash - rounded. If negative, customer underpaid -> raise error
    balance = cash_paid - rounded
    if balance < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient cash. Net payable is {rounded:.2f}, but cash paid is {cash_paid:.2f}. Short by {-balance:.2f}",
        )

    # Calculate denominations - balance is integer (rounded down already)
    denom_result, remaining, is_sufficient = calculate_denominations(int(balance), normalized_denoms)

    # Prepare bill - atomic transaction
    try:
        bill_number = generate_bill_number()
        # Ensure uniqueness (extremely low collision, but loop if needed)
        while db.query(Bill).filter(Bill.bill_number == bill_number).first():
            bill_number = generate_bill_number()

        # Decrement stock atomically within transaction
        for ci in computed_items:
            prod = ci["product"]
            prod.available_stocks -= ci["quantity"]
            db.add(prod)

        bill = Bill(
            bill_number=bill_number,
            customer_email=customer_email.strip().lower(),
            total_without_tax=totals["total_without_tax"],
            total_tax_payable=totals["total_tax_payable"],
            net_price=totals["net_price"],
            rounded_down_net_price=totals["rounded_down_net_price"],
            cash_paid=float(cash_paid),
            balance_payable=float(balance),
            denominations_returned=json.dumps(denom_result),
            created_at=datetime.utcnow(),
        )
        db.add(bill)
        db.flush()  # get bill.id

        # Create bill items
        for ci in computed_items:
            bi = BillItem(
                bill_id=bill.id,
                product_id=ci["product_id"],
                product_name=ci["product_name"],
                unit_price=ci["unit_price"],
                quantity=ci["quantity"],
                purchase_price=ci["purchase_price"],
                tax_percentage=ci["tax_percentage"],
                tax_payable=ci["tax_payable"],
                total_price=ci["total_price"],
            )
            db.add(bi)

        db.commit()
        db.refresh(bill)
        # Attach flag for insufficient change notice if needed (caller can inspect)
        # We store denominations but also need to surface warning
        # We'll add attribute dynamically
        bill._denom_remaining = remaining
        bill._denom_sufficient = is_sufficient
        return bill

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create bill: {str(e)}")
