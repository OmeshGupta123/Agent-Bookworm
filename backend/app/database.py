import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Fallback to SQLite if PostgreSQL fails to connect or isn't running
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )
    # Test connection
    with engine.connect() as conn:
        pass
    logger.info("Successfully connected to primary database.")
except Exception as e:
    logger.warning(f"Could not connect to configured DATABASE_URL ({DATABASE_URL}). Falling back to SQLite. Error: {e}")
    SQLITE_URL = "sqlite:///./agenticpay.db"
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
