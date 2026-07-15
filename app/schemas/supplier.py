from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.supplier import SupplierOrderStatus


class SupplierCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    notes: Optional[str] = None


class SupplierOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    contact_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    gst_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SupplierOrderItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal
    unit: Optional[str] = None
    unit_price: Decimal


class SupplierOrderItemOut(BaseModel):
    id: UUID
    product_id: UUID
    quantity: Decimal
    unit: Optional[str]
    entered_quantity: Optional[Decimal]
    unit_price: Decimal
    total_price: Decimal

    class Config:
        from_attributes = True


class SupplierOrderCreate(BaseModel):
    supplier_id: UUID
    items: List[SupplierOrderItemCreate]
    notes: Optional[str] = None


class SupplierOrderOut(BaseModel):
    id: UUID
    user_id: UUID
    supplier_id: UUID
    status: SupplierOrderStatus
    total_amount: Decimal
    notes: Optional[str]
    ordered_at: Optional[datetime]
    received_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    items: List[SupplierOrderItemOut]

    class Config:
        from_attributes = True


class SupplierList(BaseModel):
    total: int
    items: List[SupplierOut]
