from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from app.models.transaction import TransactionStatus, VoucherType


class LedgerEntrySchema(BaseModel):
    id: UUID
    debit_account: str
    credit_account: str
    amount: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionOut(BaseModel):
    id: UUID
    user_id: UUID
    voucher_type: VoucherType
    amount: Decimal
    party_name: str | None
    narration: str | None
    payment_mode: str | None
    status: TransactionStatus
    created_at: datetime
    ledger_entries: list[LedgerEntrySchema] = []

    class Config:
        from_attributes = True


class TransactionList(BaseModel):
    total: int
    items: list[TransactionOut]


class ConfirmEntryRequest(BaseModel):
    transaction_id: UUID
    action: str  # "confirm" | "reject"
    edited_debit_account: str | None = None
    edited_credit_account: str | None = None
    edited_amount: Decimal | None = None
    edited_narration: str | None = None


class ProcessTextRequest(BaseModel):
    text: str
    user_id: UUID | None = None
