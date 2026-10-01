import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.db.models import AuditLog

logger = logging.getLogger(__name__)


def record_audit(
    db: Session,
    actor_type: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    log_entry = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    logger.info("AUDIT: [%s:%s] %s on %s:%s", actor_type, actor_id, action, resource_type, resource_id)
    return log_entry
