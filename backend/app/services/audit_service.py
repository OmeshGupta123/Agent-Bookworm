import json
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import AIAuditLog

logger = logging.getLogger(__name__)

# Enterprise audit action types strictly logged for Merchant Dashboard
ALLOWED_AUDIT_ACTIONS = {
    'CHECKOUT_BLOCKED',
    'STOCK_CHECK_FAILED',
    'PAYMENT_VERIFIED',
    'PAYMENT_FAILED',
    'ITEM_ADDED_TO_CART',
    'ITEM_REMOVED_FROM_CART',
    'CHECKOUT_GENERATED',
    'TOOL_AUDIT',
    'PENDING_APPROVAL'
}

def log_ai_action(
    db: Session,
    action_type: str,
    ai_reasoning: str,
    amount_involved: float = 0.0,
    order_id: Optional[int] = None,
    log_metadata: Optional[Dict[str, Any]] = None
) -> Optional[AIAuditLog]:
    """
    Logs financial guardrail blocks, stock exceptions, cart mutations, and checkout/tool actions into ai_audit_logs.
    Filters out noise to maintain a high-value merchant financial audit trail.
    """
    if action_type not in ALLOWED_AUDIT_ACTIONS:
        return None

    meta_str = json.dumps(log_metadata) if log_metadata else None

    try:
        audit_entry = AIAuditLog(
            order_id=order_id,
            action_type=action_type,
            ai_reasoning=ai_reasoning,
            amount_involved=round(amount_involved, 2),
            log_metadata=meta_str
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return audit_entry
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging audit action '{action_type}': {e}")
        return None


def log_tool_audit(
    db: Session,
    tool_name: str,
    input_params: dict,
    output_result: dict,
    status: str = 'SUCCESS',
    ai_reasoning: str = '',
    amount_involved: float = 0.0,
    order_id: Optional[int] = None
) -> Optional[AIAuditLog]:
    metadata = {
        'tool_name': tool_name,
        'input_params': input_params,
        'output_result': output_result,
        'status': status
    }
    return log_ai_action(
        db=db,
        action_type='TOOL_AUDIT',
        ai_reasoning=ai_reasoning or f'Tool {tool_name} executed with status {status}.',
        amount_involved=amount_involved,
        order_id=order_id,
        log_metadata=metadata
    )
