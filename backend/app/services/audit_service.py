from typing import Optional
from sqlalchemy.orm import Session
from app.models import AIAuditLog

def log_ai_action(
    db: Session,
    action_type: str,
    ai_reasoning: str,
    amount_involved: float = 0.0,
    order_id: Optional[int] = None
) -> AIAuditLog:
    """
    Logs an explainable money or pricing action taken by the AI into ai_audit_logs.
    """
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
