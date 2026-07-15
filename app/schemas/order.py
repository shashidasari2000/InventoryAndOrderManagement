from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.order import BuyerOrderStatus


class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal
    unit: Optional[str] = None
    unit_price: Decimal


class OrderItemOut(BaseModel):
    id: UUID
    product_id: UUID
    quantity: Decimal
    unit: Optional[str] = None
    entered_quantity: Optional[Decimal] = None
    unit_price: Decimal
    cost_price_snapshot: Decimal
    total_price: Decimal

    class Config:
        from_attributes = True


class BuyerOrderCreate(BaseModel):
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    items: List[OrderItemCreate]
    discount: Decimal = Decimal("0")
    notes: Optional[str] = None


class BuyerOrderOut(BaseModel):
    id: UUID
    user_id: UUID
    buyer_name: Optional[str]
    buyer_phone: Optional[str]
    status: BuyerOrderStatus
    subtotal: Decimal
    discount: Decimal
    total_amount: Decimal
    notes: Optional[str]
    checked_out_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemOut]

    class Config:
        from_attributes = True


class BuyerOrderList(BaseModel):
    total: int
    items: List[BuyerOrderOut]
