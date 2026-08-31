from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AIAuditLog
from app.schemas import AIAuditLogResponse

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Trail"])

@router.get("", response_model=List[AIAuditLogResponse])
def get_audit_logs(db: Session = Depends(get_db)):
    """
    GET /api/audit-logs
    Returns all AI money actions and explainable reasoning timeline for the Merchant Audit Dashboard.
    """
    logs = db.query(AIAuditLog).order_by(AIAuditLog.timestamp.desc()).all()
    return logs
