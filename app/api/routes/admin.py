from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from app.database import get_db
from app.api.deps import require_admin
from app.models.user import User, RegistrationStep
from app.models.transaction import Transaction
from app.models.message import Message
from app.schemas.dashboard import AdminStats
from app.services import whatsapp_service, auth_service
import asyncio, threading
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["Admin"])


class InviteRequest(BaseModel):
    phone_number: str
    business_name: str | None = None
    custom_message: str | None = None


def _send_whatsapp_bg(phone: str, msg: str):
    def _run():
        try:
            result = asyncio.run(whatsapp_service.send_message(phone, msg))
            if not result:
                logger.warning("invite_whatsapp_failed", phone=phone)
        except Exception as e:
            logger.warning("invite_whatsapp_failed", phone=phone, error=str(e))
    threading.Thread(target=_run, daemon=True).start()


async def _send_whatsapp_async(phone: str, msg: str) -> tuple[bool, str]:
    """Send WhatsApp message and return (success, error_detail)."""
    import httpx
    from app.config import get_settings
    s = get_settings()
    if not s.WHATSAPP_ACCESS_TOKEN or not s.WHATSAPP_PHONE_NUMBER_ID:
        return False, "WhatsApp not configured"
    url = f"{s.WHATSAPP_API_URL}/{s.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {s.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    body = {"messaging_product": "whatsapp", "to": phone.lstrip("+"), "type": "text", "text": {"body": msg}}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers)
        if resp.status_code == 200:
            return True, ""
        return False, resp.text


@router.get("/config")
def get_admin_config(
    _: User = Depends(require_admin),
):
    from app.config import get_settings
    s = get_settings()
    return {"whatsapp_business_number": s.WHATSAPP_BUSINESS_NUMBER or ""}


@router.get("/stats", response_model=AdminStats)
def get_admin_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_messages = db.query(Message).count()
    total_transactions = db.query(Transaction).count()

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_messages=total_messages,
        total_transactions=total_transactions,
        system_status="healthy",
    )


@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": str(u.id),
            "phone_number": u.phone_number,
            "business_name": u.business_name,
            "is_active": u.is_active,
            "registration_step": u.registration_step.value,
            "role": u.role.value,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/invite")
async def invite_user(
    payload: InviteRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    phone = payload.phone_number.strip()
    if not phone.startswith("+"):
        raise HTTPException(status_code=400, detail="Phone number must include country code e.g. +919876543210")

    # Create user record if not exists
    user = auth_service.get_or_create_user(db, phone)

    if payload.custom_message:
        msg = payload.custom_message
    else:
        greeting = f"Hi *{payload.business_name}*! 👋\n\n" if payload.business_name else "Hi! 👋\n\n"
        msg = (
            f"{greeting}"
            f"You've been invited to *AI Accounting Assistant* 🧾\n\n"
            f"Record your business transactions simply by sending a WhatsApp message like:\n"
            f"_'Paid ₹5000 to Ramesh supplier by UPI'_\n\n"
            f"To get started, visit:\n"
            f"http://localhost:3000\n\n"
            f"Or just reply *Hi* to this message to begin!"
        )

    success, error_detail = await _send_whatsapp_async(phone, msg)
    if not success:
        logger.warning("invite_whatsapp_failed", phone=phone, detail=error_detail)
        raise HTTPException(status_code=502, detail=f"WhatsApp delivery failed: {error_detail}")

    logger.info("user_invited", phone=phone)
    return {"message": f"Invitation sent to {phone}", "user_id": str(user.id)}
