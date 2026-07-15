from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import date
from typing import Optional
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.transaction import TransactionStatus
from app.schemas.transaction import (
    TransactionOut, TransactionList, ConfirmEntryRequest, ProcessTextRequest
)
from app.schemas.dashboard import DashboardSummary, MonthlySummaryItem, SalesSummary, TopProductItem
from app.services import transaction_service, whisper_service
from app.services.ai_parser import parse_transaction
from app.models.message import MessageType
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post("/process-text", response_model=TransactionOut, status_code=201)
def process_text(
    payload: ProcessTextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        txn = transaction_service.create_pending_transaction(
            db, current_user.id, payload.text, MessageType.TEXT
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return txn


@router.post("/process-voice", response_model=TransactionOut, status_code=201)
async def process_voice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    audio_bytes = await file.read()
    try:
        transcript = whisper_service.transcribe_audio(audio_bytes, file.filename or "audio.ogg")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Transcription failed: {str(e)}")

    try:
        txn = transaction_service.create_pending_transaction(
            db, current_user.id, transcript, MessageType.VOICE
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return txn


@router.post("/confirm-entry", response_model=TransactionOut)
def confirm_entry(
    payload: ConfirmEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.action not in ("confirm", "reject", "edit"):
        raise HTTPException(status_code=400, detail="action must be 'confirm', 'reject', or 'edit'")
    try:
        txn = transaction_service.confirm_transaction(
            db,
            payload.transaction_id,
            current_user.id,
            payload.action,
            edited_debit=payload.edited_debit_account,
            edited_credit=payload.edited_credit_account,
            edited_amount=payload.edited_amount,
            edited_narration=payload.edited_narration,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return txn


@router.get("", response_model=TransactionList)
def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: TransactionStatus | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = transaction_service.get_user_transactions(
        db, current_user.id, skip=skip, limit=limit, status=status
    )
    return TransactionList(total=total, items=items)


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_dashboard_summary(db, current_user.id)


@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
def get_monthly_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_monthly_summary(db, current_user.id)


@router.get("/sales-summary", response_model=SalesSummary)
def get_sales_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_sales_summary(db, current_user.id)


@router.get("/top-products", response_model=list[TopProductItem])
def get_top_products(
    limit: int = Query(4, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_top_products(db, current_user.id, limit=limit)


@router.get("/accounts", response_model=list[str])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_all_accounts(db, current_user.id)


@router.get("/account-report")
def account_report(
    account: str = Query(..., description="Account name e.g. 'Bank A/c'"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return transaction_service.get_account_report(db, current_user.id, account, from_date, to_date)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.transaction import Transaction
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        transaction_service.delete_transaction(db, transaction_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None
