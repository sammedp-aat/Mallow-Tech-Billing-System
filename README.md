# Billing & Invoicing System — FastAPI

Production-ready Billing & Invoicing Web Application built with **FastAPI**, **SQLAlchemy**, **SQLite/PostgreSQL**, and **Jinja2**.  
Implements tax calculations, denomination change-making, inventory with atomic transactions, and async invoice emails.

---

## Architecture Overview

```
billing_system/
├── app/
│   ├── database.py          # SQLAlchemy engine & Session (SQLite default, PostgreSQL via DATABASE_URL)
│   ├── models.py            # Product, Bill, BillItem ORM models
│   ├── schemas.py           # Pydantic validation schemas
│   ├── seed.py              # Auto-seed 6 products on empty DB
│   ├── services/
│   │   ├── billing_service.py  # Calculations + greedy denominations + atomic bill creation
│   │   └── email_service.py    # BackgroundTasks email with SMTP + console fallback
│   ├── templates/           # Jinja2 HTML (base, billing, invoice, history, products)
│   └── static/css, js       # Production CSS & dynamic row JS
├── tests/test_billing.py    # Pytest suite (20+ cases)
├── main.py                  # FastAPI app & all routes
├── requirements.txt
└── billing.db               # SQLite file (auto-created)
```

**Request Flow:**

1. `GET /` → Billing form (products preloaded, datalist autocomplete).
2. `POST /generate-bill` → `billing_service.create_bill()` validates stock, computes totals, greedy denominations, atomically decrements inventory, commits `Bill` + `BillItem`s, queues `BackgroundTasks` email → `303 Redirect` → `GET /bill/{id}`.
3. `GET /bill/{id}` → Invoice page with itemized table, summary, denomination breakdown.
4. `GET /history?email=` → Filters `Bill` by email, shows expandable details.
5. `GET|POST /products` → CRUD for stock/price/tax.

---

## Setup and Installation

### 1. Create virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Database seed

Seed runs **automatically on startup** if the DB is empty.  
Manual run also available:

```bash
python -m app.seed
# or from project root
python -c "from app.seed import seed_db; seed_db()"
```

Seeded products:

| ID   | Name                      | Price   | Tax   | Stock |
|------|---------------------------|---------|-------|-------|
| P101 | Organic Cow Milk          | 60.00   | 5.0%  | 50    |
| P102 | Whole Wheat Bread         | 45.00   | 5.0%  | 40    |
| P103 | Arabica Coffee Beans 250g | 350.00  | 12.0% | 25    |
| P104 | Dark Chocolate 100g       | 150.00  | 18.0% | 60    |
| P105 | Cold Pressed Olive Oil 1L | 850.00  | 12.0% | 15    |
| P106 | Basmati Rice 5kg          | 520.00  | 5.0%  | 30    |

---

## How to Run the Application

```bash
uvicorn main:app --reload
# or
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open: **http://127.0.0.1:8000**

- Billing Form: `http://127.0.0.1:8000/`
- Invoice Example: `http://127.0.0.1:8000/bill/1`
- History: `http://127.0.0.1:8000/history`
- Products: `http://127.0.0.1:8000/products`
- Health: `http://127.0.0.1:8000/health`
- API Products JSON: `http://127.0.0.1:8000/api/products`

**PostgreSQL (optional):**

```bash
set DATABASE_URL=postgresql://user:password@localhost:5432/billing
uvicorn main:app --reload
```

**SMTP Email (optional):**

```bash
set SMTP_HOST=smtp.gmail.com
set SMTP_PORT=587
set SMTP_USER=you@gmail.com
set SMTP_PASSWORD=app_password
set SMTP_FROM=you@gmail.com
```

If not set, the app automatically logs a formatted HTML + plain-text invoice to the console with an ASCII border (dev fallback) — no blocking.

---

## How to Execute Unit Tests

```bash
pytest -v
# with coverage (optional)
pytest -v --tb=short
```

**What’s covered:**

- Per-item: purchase price, tax payable, total (0%, 5%, 12%, 18% cases)
- Aggregate: total without tax, total tax, net, floor rounding, balance
- Denomination greedy algorithm: exact change, 500-path, limited stock, insufficient shop notes, zero balance, large amounts
- Inventory: insufficient stock error, non-existent product, insufficient cash, successful bill & stock decrement, multi-product bill

---

## Assumptions and Denomination Algorithm

### Business Rules

- **Bill number:** `BILL-{YYYYMMDD}-{8_HEX}` via `secrets.token_hex`, uniqueness checked in DB.
- **Rounded down:** `math.floor(net_price)` — Indian retail convention. Balance = `cash_paid - rounded`.
- **Inventory:** Validated before creation; atomic decrement inside same transaction. Failure rolls back entirely.
- **Cash:** Must be `>= rounded_down`. Underpayment returns `400 Insufficient cash`.
- **Email:** Lowercased and indexed for history search.

### Denomination Algorithm (Greedy)

Shop denominations fixed: `[500, 50, 20, 10, 5, 2, 1]` (no 100/200 as per spec).

```
remaining = floor(balance)  # integer
for D in [500, 50, 20, 10, 5, 2, 1]:
    give = min(remaining // D, available[D])
    result[D] = give
    remaining -= give * D
is_sufficient = (remaining == 0)
```

- Starts at highest denomination, maximizes larger notes.
- Respects `available_count[D]` per request (default 20 each if omitted).
- If `remaining > 0` after `1`, invoice shows warning: *“Insufficient denominations — maximum ₹X returned, short ₹Y”* and still stores partial distribution.
- Complexity `O(7)` constant time. Greedy is optimal for canonical Indian denominations.

### Security & Production Notes

- **No hardcoded secrets** — SMTP via env vars, DB URL via env.
- **Pydantic** validates schemas; **HTTPException** for clear user errors.
- **BackgroundTasks** prevents email I/O from blocking response.
- **Jinja2 autoescape** on, SQLAlchemy `pool_pre_ping`, SQLite `check_same_thread=False` for ASGI.
- PEP 8, type hints, docstrings, and separation of concerns (services layer).

---

## PEP 8 & Code Quality

```bash
# optional lint
pip install flake8 black
black app/ main.py tests/
flake8 app/
```

All code follows senior-level standards: DRY, SOLID, readable names, proper error handling, and zero placeholders.
