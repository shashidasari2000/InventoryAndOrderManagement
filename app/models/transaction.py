import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class TransactionStatus(str, enum.Enum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EDITED = "edited"


class VoucherType(str, enum.Enum):
    PAYMENT = "payment"
    RECEIPT = "receipt"
    JOURNAL = "journal"
    PURCHASE = "purchase"
    SALES = "sales"
    EXPENSE = "expense"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    voucher_type = Column(Enum(VoucherType), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    party_name = Column(String(255), nullable=True)
    narration = Column(Text, nullable=True)
    payment_mode = Column(String(50), nullable=True)
    status = Column(
        Enum(TransactionStatus),
        default=TransactionStatus.PENDING_CONFIRMATION,
        nullable=False,
        index=True,
    )
    ai_raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user = relationship("User", back_populates="transactions")
    ledger_entries = relationship(
        "LedgerEntry", back_populates="transaction", cascade="all, delete-orphan"
    )
    message = relationship("Message", back_populates="transaction", uselist=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True
    )
    debit_account = Column(String(255), nullable=False)
    credit_account = Column(String(255), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="ledger_entries")
