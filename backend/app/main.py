import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base, SessionLocal
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
    title="AgenticPay API",
    description="Agentic Commerce Backend with Bounded Discounts, Razorpay Checkouts, Audit Logs, and Graceful Inventory Handling.",
    version="1.0.0"
)

# CORS setup for React frontend integration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    logger.info("Initializing AgenticPay database tables and seeding catalog...")
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
        "app": "AgenticPay API",
        "status": "online",
        "track": "AI Growth & Agentic Commerce (Razorpay Buildathon)",
        "max_discount_cap": "15%"
    }
