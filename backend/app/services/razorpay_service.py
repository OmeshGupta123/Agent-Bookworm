import hmac
import hashlib
import uuid
import logging
import razorpay
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger(__name__)


class RazorpayUnavailableError(RuntimeError):
    """The payment provider cannot safely create or verify a live test order."""

def get_razorpay_client():
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        try:
            return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        except Exception as e:
            logger.warning(f"Failed to initialize Razorpay Client: {e}")
    return None

def create_razorpay_payment_link(
    amount_in_inr: float,
    buyer_email: str,
    description: str = "Bookstore Checkout",
    notes: dict = None
) -> dict:
    # 1. Graceful Failure Simulation for test buyer
    if buyer_email == 'fail@test.com':
        logger.warning("Simulated 500 payment gateway error triggered for fail@test.com")
        raise Exception("Simulated 500: Razorpay payment link generation service unavailable.")

    client = get_razorpay_client()
    amount_in_paise = int(round(amount_in_inr * 100))

    if not client:
        raise RazorpayUnavailableError("Razorpay test credentials are not configured.")

    try:
        payload = {
            'amount': amount_in_paise,
            'currency': 'INR',
            'accept_partial': False,
            'description': description,
            'customer': {'email': buyer_email},
            'notify': {'sms': False, 'email': True},
            'notes': notes or {}
        }
        res = client.payment_link.create(data=payload)
        return {'id': res.get('id'), 'short_url': res.get('short_url')}
    except Exception as exc:
        logger.warning("Razorpay payment-link API failed: %s", exc)
        raise RazorpayUnavailableError("Razorpay could not create a payment link.") from exc


def create_razorpay_order_sdk(amount_in_inr: float, notes: dict = None) -> str:
    """
    Creates a Razorpay order in INR (amount converted to paise = amount * 100).
    Returns the razorpay_order_id.
    """
    client = get_razorpay_client()
    amount_in_paise = int(round(amount_in_inr * 100))
    
    if not client:
        raise RazorpayUnavailableError("Razorpay test credentials are not configured.")

    try:
        data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": f"receipt_{uuid.uuid4().hex[:10]}",
            "notes": notes or {}
        }
        res = client.order.create(data=data)
        logger.info("Created Razorpay order: %s", res["id"])
        return res["id"]
    except Exception as exc:
        logger.warning("Razorpay order API failed: %s", exc)
        raise RazorpayUnavailableError("Razorpay could not create an order.") from exc

def verify_razorpay_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Verifies Razorpay payment signature using client utility or HMAC SHA256 fallback.
    """
    client = get_razorpay_client()
    if client:
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            logger.info(f"Razorpay payment signature verified via SDK for Order: {razorpay_order_id}")
            return True
        except Exception as e:
            logger.warning(f"Razorpay SDK signature verification failed: {e}. Attempting manual HMAC verification.")

    # Manual HMAC verification logic
    try:
        generated_signature = hmac.new(
            key=RAZORPAY_KEY_SECRET.encode(),
            msg=f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(generated_signature, razorpay_signature)
    except Exception as e:
        logger.error(f"Manual HMAC verification failed: {e}")
        return False
