from decimal import Decimal
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, or_
from app.models.transaction import Transaction, LedgerEntry, TransactionStatus, VoucherType
from app.models.message import Message, MessageType
from app.models.order import BuyerOrder, OrderItem, BuyerOrderStatus
from app.models.inventory import Product
from app.services.ai_parser import parse_transaction
from app.services.encryption import encrypt_message
from app.services.audit_service import log_action
import structlog

logger = structlog.get_logger()


def create_pending_transaction(
    db: Session,
    user_id: UUID,
    raw_text: str,
    message_type: MessageType = MessageType.TEXT,
    whatsapp_message_id: str | None = None,
) -> Transaction:
    """Parse text and create a PENDING_CONFIRMATION transaction."""
    parsed = parse_transaction(raw_text)

    if parsed["amount"] is None:
        raise ValueError("Could not determine amount from the message")

    voucher_map = {
        "payment": VoucherType.PAYMENT,
        "receipt": VoucherType.RECEIPT,
        "purchase": VoucherType.PURCHASE,
        "sales": VoucherType.SALES,
        "journal": VoucherType.JOURNAL,
        "expense": VoucherType.EXPENSE,
    }
    voucher_type = voucher_map.get(parsed["voucher_type"], VoucherType.JOURNAL)

    txn = Transaction(
        user_id=user_id,
        voucher_type=voucher_type,
        amount=Decimal(str(parsed["amount"])),
        party_name=parsed.get("party"),
        narration=parsed.get("narration"),
        payment_mode=parsed.get("payment_mode"),
        status=TransactionStatus.PENDING_CONFIRMATION,
        ai_raw_response=str(parsed),
    )
    db.add(txn)
    db.flush()

    entry = LedgerEntry(
        transaction_id=txn.id,
        debit_account=parsed["debit_account"],
        credit_account=parsed["credit_account"],
        amount=Decimal(str(parsed["amount"])),
    )
    db.add(entry)

    # Store encrypted message
    msg = Message(
        user_id=user_id,
        transaction_id=txn.id,
        encrypted_content=encrypt_message(raw_text),
        message_type=message_type,
        whatsapp_message_id=whatsapp_message_id,
        is_inbound=True,
    )
    db.add(msg)
    db.commit()
    db.refresh(txn)

    log_action(db, user_id=user_id, action="transaction_created", entity_type="transaction", entity_id=str(txn.id))
    logger.info("transaction_created", txn_id=str(txn.id), user_id=str(user_id))
    return txn


def confirm_transaction(
    db: Session,
    transaction_id: UUID,
    user_id: UUID,
    action: str,
    edited_debit: str | None = None,
    edited_credit: str | None = None,
    edited_amount: Decimal | None = None,
    edited_narration: str | None = None,
) -> Transaction:
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
        Transaction.status == TransactionStatus.PENDING_CONFIRMATION,
    ).first()

    if not txn:
        raise ValueError("Transaction not found or already processed")

    if action == "reject":
        txn.status = TransactionStatus.REJECTED
        db.commit()
        log_action(db, user_id=user_id, action="transaction_rejected", entity_type="transaction", entity_id=str(txn.id))
        return txn

    if action in ("confirm", "edit"):
        if edited_amount or edited_debit or edited_credit or edited_narration:
            txn.status = TransactionStatus.EDITED
            if edited_amount:
                txn.amount = edited_amount
            if edited_narration:
                txn.narration = edited_narration
            entry = txn.ledger_entries[0] if txn.ledger_entries else None
            if entry:
                if edited_debit:
                    entry.debit_account = edited_debit
                if edited_credit:
                    entry.credit_account = edited_credit
                if edited_amount:
                    entry.amount = edited_amount
        else:
            txn.status = TransactionStatus.CONFIRMED

        db.commit()
        db.refresh(txn)
        log_action(db, user_id=user_id, action=f"transaction_{action}d", entity_type="transaction", entity_id=str(txn.id))
        return txn

    raise ValueError(f"Invalid action: {action}")


def get_user_transactions(
    db: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    status: TransactionStatus | None = None,
) -> tuple[int, list[Transaction]]:
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    if status:
        query = query.filter(Transaction.status == status)
    total = query.count()
    items = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return total, items


def get_dashboard_summary(db: Session, user_id: UUID) -> dict:
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]

    total_income = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type.in_([VoucherType.RECEIPT, VoucherType.SALES]),
        Transaction.status.in_(confirmed_statuses),
    ).scalar() or Decimal("0")

    total_expenses = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type.in_([VoucherType.PAYMENT, VoucherType.EXPENSE, VoucherType.PURCHASE]),
        Transaction.status.in_(confirmed_statuses),
    ).scalar() or Decimal("0")

    total_receivables = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type == VoucherType.SALES,
        Transaction.status.in_(confirmed_statuses),
    ).scalar() or Decimal("0")

    total_payables = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type == VoucherType.PURCHASE,
        Transaction.status.in_(confirmed_statuses),
    ).scalar() or Decimal("0")

    total_transactions = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.status.in_(confirmed_statuses),
    ).count()

    pending_confirmations = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.status == TransactionStatus.PENDING_CONFIRMATION,
    ).count()

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "total_receivables": total_receivables,
        "total_payables": total_payables,
        "total_transactions": total_transactions,
        "pending_confirmations": pending_confirmations,
    }


def list_expenses(db: Session, user_id: UUID, from_date: datetime | None = None, limit: int = 20) -> list[dict]:
    """Return list of individual expense transactions with details."""
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    expense_vouchers = [VoucherType.PAYMENT, VoucherType.EXPENSE, VoucherType.PURCHASE]

    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type.in_(expense_vouchers),
        Transaction.status.in_(confirmed_statuses),
    )

    if from_date:
        query = query.filter(Transaction.created_at >= from_date)

    transactions = (
        query.order_by(Transaction.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(t.id),
            "narration": t.narration or t.party_name or "Expense",
            "amount": float(t.amount),
            "created_at": t.created_at,
        }
        for t in transactions
    ]


def delete_transaction(db: Session, transaction_id: UUID, user_id: UUID) -> None:
    """Delete a transaction and its ledger entries."""
    txn = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if not txn:
        raise ValueError("Transaction not found")
    # Delete associated ledger entries first
    db.query(LedgerEntry).filter(LedgerEntry.transaction_id == transaction_id).delete()
    # Delete the transaction
    db.delete(txn)
    db.commit()


def list_incomes(db: Session, user_id: UUID, from_date: datetime | None = None, limit: int = 20) -> list[dict]:
    """Return list of individual income transactions with details."""
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    income_vouchers = [VoucherType.RECEIPT, VoucherType.SALES]

    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type.in_(income_vouchers),
        Transaction.status.in_(confirmed_statuses),
    )

    if from_date:
        query = query.filter(Transaction.created_at >= from_date)

    transactions = (
        query.order_by(Transaction.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(t.id),
            "narration": t.narration or t.party_name or "Income",
            "amount": float(t.amount),
            "created_at": t.created_at,
        }
        for t in transactions
    ]


def get_monthly_summary(db: Session, user_id: UUID) -> list[dict]:
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    rows = (
        db.query(
            extract("year", Transaction.created_at).label("year"),
            extract("month", Transaction.created_at).label("month"),
            Transaction.voucher_type,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.status.in_(confirmed_statuses),
        )
        .group_by("year", "month", Transaction.voucher_type)
        .order_by("year", "month")
        .all()
    )

    summary: dict[str, dict] = {}
    for row in rows:
        key = f"{int(row.year)}-{int(row.month):02d}"
        if key not in summary:
            summary[key] = {"month": key, "income": Decimal("0"), "expenses": Decimal("0")}
        if row.voucher_type in (VoucherType.RECEIPT, VoucherType.SALES):
            summary[key]["income"] += row.total
        else:
            summary[key]["expenses"] += row.total

    return list(summary.values())


def get_all_accounts(db: Session, user_id: UUID) -> list[str]:
    """Return sorted list of all unique account names from confirmed ledger entries."""
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    rows = (
        db.query(LedgerEntry.debit_account, LedgerEntry.credit_account)
        .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.status.in_(confirmed_statuses),
        )
        .all()
    )
    accounts: set[str] = set()
    for debit, credit in rows:
        accounts.add(debit)
        accounts.add(credit)
    return sorted(accounts)


def get_account_report(
    db: Session,
    user_id: UUID,
    account: str,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Returns all ledger entries for a given account within a date range,
    plus opening balance, total debits, total credits, and closing balance.
    """
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]

    query = (
        db.query(LedgerEntry, Transaction)
        .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.status.in_(confirmed_statuses),
            or_(
                LedgerEntry.debit_account == account,
                LedgerEntry.credit_account == account,
            ),
        )
    )

    if from_date:
        query = query.filter(Transaction.created_at >= from_date)
    if to_date:
        from datetime import datetime, time
        end_dt = datetime.combine(to_date, time.max)
        query = query.filter(Transaction.created_at <= end_dt)

    rows = query.order_by(Transaction.created_at.asc()).all()

    entries = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    running_balance = Decimal("0")

    for entry, txn in rows:
        is_debit = entry.debit_account == account
        amount = Decimal(str(entry.amount))
        if is_debit:
            total_debit += amount
            running_balance += amount
        else:
            total_credit += amount
            running_balance -= amount

        entries.append({
            "date": txn.created_at.isoformat(),
            "narration": txn.narration or "",
            "party": txn.party_name or "",
            "voucher_type": txn.voucher_type.value if hasattr(txn.voucher_type, "value") else str(txn.voucher_type),
            "debit": float(amount) if is_debit else None,
            "credit": float(amount) if not is_debit else None,
            "balance": float(running_balance),
            "transaction_id": str(txn.id),
        })

    return {
        "account": account,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "total_debit": float(total_debit),
        "total_credit": float(total_credit),
        "closing_balance": float(running_balance),
        "entries": entries,
    }


def get_sales_summary(db: Session, user_id: UUID) -> dict:
    """Return confirmed sales for today, this week, and this month."""
    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    week_start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
    month_start = datetime.combine(now.date().replace(day=1), datetime.min.time())

    def sales_for(start: datetime) -> Decimal:
        total = db.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == user_id,
            Transaction.voucher_type.in_([VoucherType.RECEIPT, VoucherType.SALES]),
            Transaction.status.in_(confirmed_statuses),
            Transaction.created_at >= start,
        ).scalar() or Decimal("0")
        return total

    return {
        "today": sales_for(today_start),
        "this_week": sales_for(week_start),
        "this_month": sales_for(month_start),
    }


def get_top_products(db: Session, user_id: UUID, limit: int = 4) -> list[dict]:
    """Return top selling products by confirmed buyer order quantity."""
    rows = (
        db.query(
            OrderItem.product_id,
            Product.name,
            Product.sku,
            Product.unit,
            func.sum(OrderItem.quantity).label("quantity_sold"),
            func.sum(OrderItem.total_price).label("total_revenue"),
        )
        .join(BuyerOrder, BuyerOrder.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(
            BuyerOrder.user_id == user_id,
            BuyerOrder.status == BuyerOrderStatus.CONFIRMED,
        )
        .group_by(OrderItem.product_id, Product.name, Product.sku, Product.unit)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": row.product_id,
            "name": row.name,
            "sku": row.sku,
            "unit": row.unit,
            "quantity_sold": row.quantity_sold or Decimal("0"),
            "total_revenue": row.total_revenue or Decimal("0"),
        }
        for row in rows
    ]

