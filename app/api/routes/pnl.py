from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.pnl import PnLSummary
from app.services import pnl_service

router = APIRouter(prefix="/pnl", tags=["Profit & Loss"])


@router.get("", response_model=PnLSummary)
def get_pnl(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return pnl_service.get_pnl(db, current_user.id, from_date=from_date, to_date=to_date)
