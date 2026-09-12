"""
Seed data - auto-run on startup if DB is empty.
Can also be run manually: python -m app.seed
"""
from app.database import SessionLocal, engine, Base
from app.models import Product

SEED_PRODUCTS = [
    {"product_id": "P101", "name": "Organic Cow Milk", "price_per_unit": 60.00, "tax_percentage": 5.0, "available_stocks": 50},
    {"product_id": "P102", "name": "Whole Wheat Bread", "price_per_unit": 45.00, "tax_percentage": 5.0, "available_stocks": 40},
    {"product_id": "P103", "name": "Arabica Coffee Beans 250g", "price_per_unit": 350.00, "tax_percentage": 12.0, "available_stocks": 25},
    {"product_id": "P104", "name": "Dark Chocolate 100g", "price_per_unit": 150.00, "tax_percentage": 18.0, "available_stocks": 60},
    {"product_id": "P105", "name": "Cold Pressed Olive Oil 1L", "price_per_unit": 850.00, "tax_percentage": 12.0, "available_stocks": 15},
    {"product_id": "P106", "name": "Basmati Rice 5kg", "price_per_unit": 520.00, "tax_percentage": 5.0, "available_stocks": 30},
]


def seed_db():
    """Create tables and seed products if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        count = db.query(Product).count()
        if count > 0:
            print(f"[Seed] Database already has {count} products. Skipping seed.")
            return

        for p in SEED_PRODUCTS:
            prod = Product(**p)
            db.add(prod)
        db.commit()
        print(f"[Seed] Seeded {len(SEED_PRODUCTS)} products successfully.")
        for p in SEED_PRODUCTS:
            print(f"  - {p['product_id']}: {p['name']} (Rs.{p['price_per_unit']}, Stock: {p['available_stocks']})")
    except Exception as e:
        db.rollback()
        print(f"[Seed] Error seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()
