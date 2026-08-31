import logging
from typing import Optional
from sqlalchemy.orm import Session
from app.models import AIAuditLog

logger = logging.getLogger(__name__)

# Allowed enterprise commerce & safety audit action types
ALLOWED_AUDIT_ACTIONS = {
    "ITEM_ADDED_TO_CART",
    "ITEM_REMOVED_FROM_CART",
    "CHECKOUT_GENERATED",
    "CHECKOUT_BLOCKED",
    "STOCK_CHECK_FAILED",
    "PAYMENT_VERIFIED",
    "PAYMENT_FAILED",
    "DISCOUNT_APPLIED"
}

def log_ai_action(
    db: Session,
    action_type: str,
    ai_reasoning: str,
    amount_involved: float = 0.0,
    order_id: Optional[int] = None
) -> Optional[AIAuditLog]:
    """
    Logs an explainable money, inventory, or discount action taken by the AI into ai_audit_logs.
    Filters out generic intent/chat noise to maintain an enterprise-grade financial audit trail.
    """
    # Filter out generic chat message logging noise
    if action_type not in ALLOWED_AUDIT_ACTIONS:
        return None

    try:
        audit_entry = AIAuditLog(
            order_id=order_id,
            action_type=action_type,
            ai_reasoning=ai_reasoning,
            amount_involved=round(amount_involved, 2)
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return audit_entry
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging audit action '{action_type}': {e}")
        return None
