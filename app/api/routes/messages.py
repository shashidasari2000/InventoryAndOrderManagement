from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.message import MessageList, MessageOut, SupportAccessRequest, SupportAccessOut
from app.services.message_service import get_user_messages, grant_support_access
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get("", response_model=MessageList)
def list_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = get_user_messages(db, current_user.id, skip=skip, limit=limit)
    return MessageList(total=total, items=items)


@router.post("/grant-support-access", response_model=SupportAccessOut)
def grant_support(
    payload: SupportAccessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.duration not in ("24h", "7d"):
        raise HTTPException(status_code=400, detail="duration must be '24h' or '7d'")
    access = grant_support_access(
        db, current_user.id, payload.duration, current_user.phone_number
    )
    return access
