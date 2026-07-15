from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from decimal import Decimal


class PnLItem(BaseModel):
    product_id: str
    product_name: str
    units_sold: Decimal
    revenue: Decimal
    cost_of_goods: Decimal
    gross_profit: Decimal


class PnLSummary(BaseModel):
    from_date: Optional[date]
    to_date: Optional[date]
    total_revenue: Decimal
    total_cost_of_goods: Decimal
    gross_profit: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    items: List[PnLItem]
