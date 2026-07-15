from uuid import UUID
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
import structlog

logger = structlog.get_logger()


def log_action(
    db: Session,
    user_id: UUID,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    performed_by: str | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        extra_data=metadata,
        ip_address=ip_address,
        performed_by=performed_by,
    )
    db.add(log)
    db.commit()
    logger.info("audit_log", user_id=str(user_id), action=action)
    return log
