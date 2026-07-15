import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class BuyerOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]


class BuyerOrder(Base):
    __tablename__ = "buyer_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    buyer_name = Column(String(255), nullable=True)
    buyer_phone = Column(String(30), nullable=True)
    status = Column(
        Enum(BuyerOrderStatus, values_callable=_enum_values),
        default=BuyerOrderStatus.DRAFT,
        nullable=False,
    )
    subtotal = Column(Numeric(15, 2), nullable=False, default=0)
    discount = Column(Numeric(15, 2), nullable=False, default=0)
    total_amount = Column(Numeric(15, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    checked_out_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="buyer_orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("buyer_orders.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(15, 3), nullable=False)
    unit = Column(String(50), nullable=True)
    entered_quantity = Column(Numeric(15, 3), nullable=True)
    unit_price = Column(Numeric(15, 2), nullable=False)
    cost_price_snapshot = Column(Numeric(15, 2), nullable=False)
    total_price = Column(Numeric(15, 2), nullable=False)

    order = relationship("BuyerOrder", back_populates="items")
    product = relationship("Product", back_populates="order_items")
