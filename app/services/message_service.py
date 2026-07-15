from uuid import UUID
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.models.message import Message
from app.models.support_access import SupportAccess
from app.services.encryption import decrypt_message
from app.services.audit_service import log_action
import structlog

logger = structlog.get_logger()


def get_user_messages(
    db: Session, user_id: UUID, skip: int = 0, limit: int = 50
) -> tuple[int, list[dict]]:
    query = db.query(Message).filter(Message.user_id == user_id)
    total = query.count()
    msgs = query.order_by(Message.created_at.desc()).offset(skip).limit(limit).all()

    results = []
    for m in msgs:
        try:
            content = decrypt_message(m.encrypted_content)
        except Exception:
            content = "[Decryption error]"
        results.append({
            "id": m.id,
            "message_type": m.message_type,
            "decrypted_content": content,
            "is_inbound": m.is_inbound,
            "created_at": m.created_at,
            "transaction_id": m.transaction_id,
        })
    return total, results


def grant_support_access(
    db: Session, user_id: UUID, duration: str, phone_number: str
) -> SupportAccess:
    hours_map = {"24h": 24, "7d": 168}
    hours = hours_map.get(duration, 24)
    expires_at = datetime.utcnow() + timedelta(hours=hours)

    # Deactivate existing access grants
    db.query(SupportAccess).filter(
        SupportAccess.user_id == user_id, SupportAccess.is_active == True
    ).update({"is_active": False})

    access = SupportAccess(
        user_id=user_id,
        granted_by_phone=phone_number,
        access_duration_hours=duration,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(access)
    db.commit()
    db.refresh(access)

    log_action(
        db,
        user_id=user_id,
        action="support_access_granted",
        metadata={"duration": duration, "expires_at": str(expires_at)},
        performed_by=phone_number,
    )
    return access


def check_support_access(db: Session, user_id: UUID) -> bool:
    access = db.query(SupportAccess).filter(
        SupportAccess.user_id == user_id,
        SupportAccess.is_active == True,
        SupportAccess.expires_at > datetime.utcnow(),
    ).first()
    return access is not None
