import hmac
from typing import List

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app.config import AUDIT_CLEAR_TOKEN
from app.database import get_db
from app.models import AIAuditLog
from app.schemas import AIAuditLogResponse

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Trail"])

ALLOWED_FINANCIAL_ACTIONS = [
    "PAYMENT_VERIFIED",
    "PAYMENT_FAILED",
    "CHECKOUT_BLOCKED",
    "STOCK_CHECK_FAILED"
]

@router.get("", response_model=List[AIAuditLogResponse])
def get_audit_logs(db: Session = Depends(get_db)):
    """
    GET /api/audit-logs
    Returns strictly financial & safety audit events:
    - PAYMENT_VERIFIED (Verified Payments)
    - PAYMENT_FAILED (Failed Payments)
    - CHECKOUT_BLOCKED (Gated Cap Blocks)
    - STOCK_CHECK_FAILED (Stock Exceptions)
    Nothing else is returned.
    """
    logs = (
        db.query(AIAuditLog)
        .filter(AIAuditLog.action_type.in_(ALLOWED_FINANCIAL_ACTIONS))
        .order_by(AIAuditLog.timestamp.desc())
        .all()
    )
    return logs

@router.post("/clear")
def clear_audit_logs(
    x_audit_clear_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    POST /api/audit-logs/clear
    Clears all AI audit log entries for a fresh demonstration or maintenance session.
    """
    if AUDIT_CLEAR_TOKEN:
        if not x_audit_clear_token or not hmac.compare_digest(x_audit_clear_token, AUDIT_CLEAR_TOKEN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Audit deletion requires valid X-Audit-Clear-Token header.",
            )
    db.query(AIAuditLog).delete()
    db.commit()
    return {"status": "success", "message": "Audit logs cleared successfully."}
