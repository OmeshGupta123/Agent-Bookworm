# app/agent/client.py
# ---------------------------------------------------------------------------
# Groq API client singleton.
# Using a module-level singleton ensures only ONE HTTP connection pool is
# created for the entire application lifetime, instead of one per request.
# ---------------------------------------------------------------------------
import logging
from groq import Groq
from app.config import GROQ_API_KEY

logger = logging.getLogger(__name__)

_client: Groq | None = None


def get_groq_client() -> Groq | None:
    """Returns the shared Groq client, initialising it once on first call."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set — Groq features disabled.")
            return None
        try:
            _client = Groq(api_key=GROQ_API_KEY)
            logger.info("Groq client initialised.")
        except Exception as exc:
            logger.error(f"Failed to initialise Groq client: {exc}")
            return None
    return _client


def get_gemini_client():
    """Backwards-compatible alias for get_groq_client."""
    return get_groq_client()

