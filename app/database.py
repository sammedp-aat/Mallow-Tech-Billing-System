"""
Database configuration for Billing System.
Supports SQLite (default) and PostgreSQL via DATABASE_URL env var.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Default to SQLite file in project root for zero-config run
# Allow override via DATABASE_URL (e.g., postgresql://user:pass@host/db)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./billing.db")

# SQLite needs check_same_thread=False for FastAPI concurrency
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
