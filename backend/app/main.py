import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import engine, Base, SessionLocal, get_db
from app.models import Product
from app.api import products, orders, audit, chat
from app.api.products import seed_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create/recreate database tables cleanly with CASCADE
try:
    with engine.connect() as conn:
        conn.execute(Base.metadata.schema and text("") or text("DROP TABLE IF EXISTS ai_audit_logs, orders, products CASCADE;"))
        conn.commit()
except Exception as e:
    logger.warning(f"Note on dropping legacy tables: {e}")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Agent Bookworm API",
    description="Agentic Commerce Backend with Bounded Discounts, Razorpay Checkouts, Audit Logs, and Graceful Inventory Handling.",
    version="1.0.0"
)

# CORS setup for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://agent-bookworm.vercel.app"  # Added your exact production Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(audit.router)

@app.on_event("startup")
def startup_event():
    logger.info("Initializing Agent Bookworm database tables and seeding catalog...")
    db = SessionLocal()
    try:
        seed_products(db)
    except Exception as e:
        logger.error(f"Error seeding database on startup: {e}")
    finally:
        db.close()

@app.get("/")
def root():
    return {
        "app": "Agent Bookworm API",
        "status": "online",
        "track": "AI Growth & Agentic Commerce (Razorpay Buildathon)",
        "max_discount_cap": "15%"
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
        "bounded_discount_cap": "15%",
        "total_products": len(catalog_data),
        "catalog": catalog_data
    }