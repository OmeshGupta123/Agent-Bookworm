import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal, get_db
from app.config import MAX_DISCOUNT_PERCENT
from app.models import Product, Order, AIAuditLog
from app.api import products, orders, audit, chat
from app.api.products import seed_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Recreate tables idempotently
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Agent Bookworm database tables and seeding catalog...")
    db = SessionLocal()
    try:
        # Purge existing audit logs and orders on new server start so the Merchant Dashboard starts fresh
        deleted_logs = db.query(AIAuditLog).delete()
        deleted_orders = db.query(Order).delete()
        db.commit()
        logger.info(f"Merchant Audit Dashboard initialized clean: purged {deleted_logs} old logs and {deleted_orders} old orders.")
        seed_products(db)
    except Exception as e:
        logger.error(f"Error initializing database on startup: {e}")
        db.rollback()
    finally:
        db.close()
    yield

app = FastAPI(
    title="Agent Bookworm API",
    description="Agentic Commerce Backend with Bounded Discounts, Razorpay Checkouts, Audit Logs, and Graceful Inventory Handling.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS setup for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(audit.router)

@app.get("/")
def root():
    return {
        "app": "Agent Bookworm API",
        "status": "online",
        "track": "AI Growth & Agentic Commerce (Razorpay Buildathon)",
        "max_discount_cap": f"{MAX_DISCOUNT_PERCENT:.0f}%"
    }

@app.get("/api/agent-catalog.json")
def get_agent_catalog(db: Session = Depends(get_db)):
    """
    Standalone Agent-to-Agent Commerce Endpoint.
    Returns a minified, agent-readable JSON schema of all products in the database.
    """
    products = db.query(Product).all()
    if not products:
        seed_products(db)
        products = db.query(Product).all()

    catalog_data = [
        {
            "id": p.id,
            "title": p.name,
            "author": p.author,
            "genre": p.genre,
            "format": p.format,
            "price": float(p.price),
            "currency": "INR",
            "stock_quantity": p.stock_quantity,
            "checkout_capability": True,
            "description": p.description
        }
        for p in products
    ]

    return {
        "store_name": "Agent Bookworm Bookstore",
        "protocol": "Agent-to-Agent Commerce v1.0",
        "checkout_capability": True,
        "bounded_discount_cap": f"{MAX_DISCOUNT_PERCENT:.0f}%",
        "total_products": len(catalog_data),
        "catalog": catalog_data
    }
