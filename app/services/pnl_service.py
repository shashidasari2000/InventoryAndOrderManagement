from decimal import Decimal
from uuid import UUID
from datetime import date, datetime, time
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.order import BuyerOrder, OrderItem, BuyerOrderStatus
from app.models.inventory import Product
from app.models.transaction import Transaction, TransactionStatus, VoucherType
from app.schemas.pnl import PnLSummary, PnLItem


def get_pnl(
    db: Session,
    user_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> PnLSummary:
    query = (
        db.query(BuyerOrder)
        .filter(
            BuyerOrder.user_id == user_id,
            BuyerOrder.status == BuyerOrderStatus.CONFIRMED,
        )
    )
    if from_date:
        query = query.filter(BuyerOrder.checked_out_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(BuyerOrder.checked_out_at <= datetime.combine(to_date, time.max))

    orders = query.all()

    product_map: dict[str, dict] = {}
    for order in orders:
        for item in order.items:
            pid = str(item.product_id)
            if pid not in product_map:
                product = db.query(Product).filter(Product.id == item.product_id).first()
                product_map[pid] = {
                    "product_id": pid,
                    "product_name": product.name if product else pid,
                    "units_sold": Decimal("0"),
                    "revenue": Decimal("0"),
                    "cost_of_goods": Decimal("0"),
                }
            product_map[pid]["units_sold"] += item.quantity
            product_map[pid]["revenue"] += item.total_price
            product_map[pid]["cost_of_goods"] += item.cost_price_snapshot * item.quantity

    items = []
    total_revenue = Decimal("0")
    total_cogs = Decimal("0")
    for p in product_map.values():
        gross = p["revenue"] - p["cost_of_goods"]
        items.append(PnLItem(
            product_id=p["product_id"],
            product_name=p["product_name"],
            units_sold=p["units_sold"],
            revenue=p["revenue"],
            cost_of_goods=p["cost_of_goods"],
            gross_profit=gross,
        ))
        total_revenue += p["revenue"]
        total_cogs += p["cost_of_goods"]

    confirmed_statuses = [TransactionStatus.CONFIRMED, TransactionStatus.EDITED]
    expense_query = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.voucher_type.in_([VoucherType.EXPENSE, VoucherType.PAYMENT, VoucherType.PURCHASE]),
        Transaction.status.in_(confirmed_statuses),
    )
    if from_date:
        expense_query = expense_query.filter(Transaction.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        expense_query = expense_query.filter(Transaction.created_at <= datetime.combine(to_date, time.max))

    total_expenses = expense_query.scalar() or Decimal("0")
    gross_profit = total_revenue - total_cogs
    net_profit = gross_profit - total_expenses

    return PnLSummary(
        from_date=from_date,
        to_date=to_date,
        total_revenue=total_revenue,
        total_cost_of_goods=total_cogs,
        gross_profit=gross_profit,
        total_expenses=total_expenses,
        net_profit=net_profit,
        items=items,
    )
