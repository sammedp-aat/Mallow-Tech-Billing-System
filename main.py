"""
FastAPI Billing & Invoicing System - Main Application
"""
import json
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Depends, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base, get_db
from app.models import Product, Bill
from app.seed import seed_db
from app.services.billing_service import create_bill, DENOMINATIONS
from app.services.email_service import send_invoice_email


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables and seed
    Base.metadata.create_all(bind=engine)
    try:
        seed_db()
    except Exception as e:
        print(f"[Startup] Seed error: {e}")
    yield


app = FastAPI(
    title="Billing & Invoicing System",
    description="Production-ready Billing System with Tax & Denomination Handling",
    version="1.0.0",
    lifespan=lifespan,
)

# Ensure tables exist even if lifespan not triggered (e.g., TestClient without context manager)
Base.metadata.create_all(bind=engine)
try:
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if "products" in inspector.get_table_names():
        _db = SessionLocal()
        try:
            if _db.query(Product).count() == 0:
                seed_db()
        finally:
            _db.close()
except Exception:
    pass

# Templates & Static
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---------- Helpers ----------
def get_all_products(db: Session):
    return db.query(Product).order_by(Product.product_id).all()


def bill_to_dict(bill: Bill):
    """Convert Bill ORM to dict for email/template."""
    items = []
    for it in bill.items:
        items.append({
            "product_id": it.product_id,
            "product_name": it.product_name,
            "unit_price": it.unit_price,
            "quantity": it.quantity,
            "purchase_price": it.purchase_price,
            "tax_percentage": it.tax_percentage,
            "tax_payable": it.tax_payable,
            "total_price": it.total_price,
        })
    denom = bill.denominations_returned or "{}"
    try:
        denom_obj = json.loads(denom) if isinstance(denom, str) else denom
    except:
        denom_obj = {}
    return {
        "id": bill.id,
        "bill_number": bill.bill_number,
        "customer_email": bill.customer_email,
        "total_without_tax": bill.total_without_tax,
        "total_tax_payable": bill.total_tax_payable,
        "net_price": bill.net_price,
        "rounded_down_net_price": bill.rounded_down_net_price,
        "cash_paid": bill.cash_paid,
        "balance_payable": bill.balance_payable,
        "denominations_returned": denom_obj,
        "denominations_raw": denom,
        "created_at": bill.created_at.strftime("%Y-%m-%d %H:%M:%S") if bill.created_at else "",
        "items": items,
    }


# ---------- Routes ----------

@app.get("/", response_class=HTMLResponse)
async def billing_form(request: Request, db: Session = Depends(get_db)):
    products = get_all_products(db)
    return templates.TemplateResponse(request, "billing.html", {
        "products": products,
        "denominations": DENOMINATIONS,
        "error": None,
    })


@app.post("/generate-bill")
async def generate_bill(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    form = await request.form()
    customer_email = str(form.get("customer_email", "")).strip()
    cash_paid_raw = form.get("cash_paid", "0")

    # Validate email
    if not customer_email or "@" not in customer_email:
        products = get_all_products(db)
        return templates.TemplateResponse(request, "billing.html", {
            "products": products,
            "denominations": DENOMINATIONS,
            "error": "Valid customer email is required.",
        }, status_code=400)

    try:
        cash_paid = float(cash_paid_raw)
    except:
        products = get_all_products(db)
        return templates.TemplateResponse(request, "billing.html", {
            "products": products,
            "denominations": DENOMINATIONS,
            "error": "Invalid cash paid amount.",
        }, status_code=400)

    # Parse product rows - form has multiple product_id and quantity
    product_ids = form.getlist("product_id") if hasattr(form, "getlist") else []
    quantities = form.getlist("quantity") if hasattr(form, "getlist") else []

    # Fallback for Starlette FormData: it stores as multi dict
    if not product_ids:
        product_ids = [v for k, v in form.items() if k == "product_id"]
        quantities = [v for k, v in form.items() if k == "quantity"]

    items_input = []
    for pid, qty in zip(product_ids, quantities):
        pid = str(pid).strip()
        if not pid:
            continue
        try:
            q = int(qty)
        except:
            continue
        if q <= 0:
            continue
        items_input.append({"product_id": pid, "quantity": q})

    if not items_input:
        products = get_all_products(db)
        return templates.TemplateResponse(request, "billing.html", {
            "products": products,
            "denominations": DENOMINATIONS,
            "error": "Add at least one product with valid quantity.",
        }, status_code=400)

    # Parse denominations
    available_denoms = {}
    for d in DENOMINATIONS:
        key = f"denom_{d}"
        raw = form.get(key, "20")
        try:
            available_denoms[d] = int(raw)
        except:
            available_denoms[d] = 20
        if available_denoms[d] < 0:
            available_denoms[d] = 0

    # Create bill
    try:
        bill = create_bill(
            db=db,
            customer_email=customer_email,
            items_input=items_input,
            cash_paid=cash_paid,
            available_denominations=available_denoms,
        )
    except HTTPException as he:
        products = get_all_products(db)
        return templates.TemplateResponse(request, "billing.html", {
            "products": products,
            "denominations": DENOMINATIONS,
            "error": he.detail,
        }, status_code=he.status_code)
    except Exception as e:
        products = get_all_products(db)
        return templates.TemplateResponse(request, "billing.html", {
            "products": products,
            "denominations": DENOMINATIONS,
            "error": f"Unexpected error: {str(e)}",
        }, status_code=500)

    # Background email
    bill_data = bill_to_dict(bill)
    background_tasks.add_task(send_invoice_email, bill.customer_email, bill_data)

    # Redirect to invoice page
    return RedirectResponse(url=f"/bill/{bill.id}", status_code=303)


@app.get("/bill/{bill_id}", response_class=HTMLResponse)
async def view_bill(request: Request, bill_id: int, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    bill_data = bill_to_dict(bill)
    denom_obj = bill_data["denominations_returned"]
    # Compute remaining logic: sum returned vs balance
    try:
        # keys may be str or int
        total_returned = sum(int(k) * int(v) for k, v in denom_obj.items()) if isinstance(denom_obj, dict) else 0
    except:
        total_returned = 0
    remaining = int(bill.balance_payable) - total_returned
    is_insufficient = remaining > 0

    return templates.TemplateResponse(request, "invoice.html", {
        "bill": bill_data,
        "denominations": DENOMINATIONS,
        "total_returned": total_returned,
        "remaining": remaining,
        "is_insufficient": is_insufficient,
    })


@app.get("/history", response_class=HTMLResponse)
async def purchase_history(request: Request, email: Optional[str] = None, db: Session = Depends(get_db)):
    bills = []
    search_email = (email or "").strip().lower()
    if search_email:
        bills = db.query(Bill).filter(Bill.customer_email == search_email).order_by(Bill.created_at.desc()).all()
        bills = [bill_to_dict(b) for b in bills]
    return templates.TemplateResponse(request, "history.html", {
        "bills": bills,
        "search_email": search_email,
        "denominations": DENOMINATIONS,
    })


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request, db: Session = Depends(get_db)):
    products = get_all_products(db)
    return templates.TemplateResponse(request, "products.html", {
        "products": products,
        "error": None,
        "success": None,
    })


@app.post("/products/create")
async def create_product(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    product_id = str(form.get("product_id", "")).strip().upper()
    name = str(form.get("name", "")).strip()
    stocks_raw = form.get("available_stocks", "0")
    price_raw = form.get("price_per_unit", "0")
    tax_raw = form.get("tax_percentage", "0")

    error = None
    success = None

    # Validation
    if not product_id or not name:
        error = "Product ID and Name are required."
    else:
        try:
            stocks = int(stocks_raw)
            price = float(price_raw)
            tax = float(tax_raw)
            if stocks < 0 or price < 0 or tax < 0 or tax > 100:
                raise ValueError()
        except:
            error = "Invalid stocks, price or tax values."

    if not error:
        existing = db.query(Product).filter(Product.product_id == product_id).first()
        if existing:
            existing.name = name
            existing.available_stocks = int(stocks_raw)
            existing.price_per_unit = float(price_raw)
            existing.tax_percentage = float(tax_raw)
            db.commit()
            success = f"Product {product_id} updated successfully."
        else:
            new_prod = Product(
                product_id=product_id,
                name=name,
                available_stocks=int(stocks_raw),
                price_per_unit=float(price_raw),
                tax_percentage=float(tax_raw),
            )
            db.add(new_prod)
            try:
                db.commit()
                success = f"Product {product_id} created successfully."
            except Exception as e:
                db.rollback()
                error = f"Failed to create product: {str(e)}"

    products = get_all_products(db)
    return templates.TemplateResponse(request, "products.html", {
        "products": products,
        "error": error,
        "success": success,
    })


@app.post("/products/update/{prod_id}")
async def update_stock(
    request: Request,
    prod_id: int,
    db: Session = Depends(get_db),
):
    form = await request.form()
    action = form.get("action", "update")

    product = db.query(Product).filter(Product.id == prod_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if action == "delete":
        db.delete(product)
        db.commit()
        return RedirectResponse(url="/products", status_code=303)

    try:
        if "available_stocks" in form:
            product.available_stocks = int(form.get("available_stocks"))
        if "price_per_unit" in form:
            product.price_per_unit = float(form.get("price_per_unit"))
        if "tax_percentage" in form:
            product.tax_percentage = float(form.get("tax_percentage"))
        if "name" in form:
            product.name = str(form.get("name")).strip() or product.name
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return RedirectResponse(url="/products", status_code=303)


@app.get("/api/products")
async def api_products(db: Session = Depends(get_db)):
    products = get_all_products(db)
    return [
        {
            "product_id": p.product_id,
            "name": p.name,
            "available_stocks": p.available_stocks,
            "price_per_unit": p.price_per_unit,
            "tax_percentage": p.tax_percentage,
        }
        for p in products
    ]


@app.get("/health")
async def health():
    return {"status": "ok"}
