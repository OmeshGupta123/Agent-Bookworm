import os
from dotenv import load_dotenv

# Load .env file from root directory or current dir
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_TV4evSxVgchq96")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "U7A0FYCOv59mycrB6IE4KCOn")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/AgentCart")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MAX_DISCOUNT_PERCENT = 15.0
