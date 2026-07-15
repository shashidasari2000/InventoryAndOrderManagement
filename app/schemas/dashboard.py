from pydantic import BaseModel
from decimal import Decimal
from uuid import UUID
from typing import Optional


class DashboardSummary(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    total_receivables: Decimal
    total_payables: Decimal
    total_transactions: int
    pending_confirmations: int


class MonthlySummaryItem(BaseModel):
    month: str
    income: Decimal
    expenses: Decimal


class SalesSummary(BaseModel):
    today: Decimal
    this_week: Decimal
    this_month: Decimal


class TopProductItem(BaseModel):
    product_id: UUID
    name: str
    sku: Optional[str]
    unit: Optional[str]
    quantity_sold: Decimal
    total_revenue: Decimal


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_messages: int
    total_transactions: int
    system_status: str
