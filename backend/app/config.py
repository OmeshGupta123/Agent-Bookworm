import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Ensure .env is resolved from the backend directory and project root
backend_env = Path(__file__).resolve().parent.parent / '.env'
root_env = Path(__file__).resolve().parent.parent.parent / '.env'

if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
elif root_env.exists():
    load_dotenv(dotenv_path=root_env)
else:
    load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
# Keep the commercial policy in one place. The UI, documentation and original
# buildathon rules advertise a 15% cap, so the application default must not
# silently allow a different value. A merchant can still override this in .env.
MAX_DISCOUNT_PERCENT = float(os.getenv("MAX_DISCOUNT_PERCENT", 15.0))
HUMAN_GATE_THRESHOLD = float(os.getenv("HUMAN_GATE_THRESHOLD", 100000.0))
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
# The browser never receives this token. It protects the destructive audit
# maintenance endpoint for local demos or an authenticated merchant console.
AUDIT_CLEAR_TOKEN = os.getenv("AUDIT_CLEAR_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/AgentCart")

if not GROQ_API_KEY:
    print("[CONFIG ERROR] GROQ_API_KEY is missing from environment or .env on startup")
    logger.warning("[CONFIG ERROR] GROQ_API_KEY is missing from environment or .env on startup")
