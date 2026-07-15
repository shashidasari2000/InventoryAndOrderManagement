import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey, Enum, Text, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class MovementType(str, enum.Enum):
    IN = "in"
    OUT = "out"
    ADJUSTMENT = "adjustment"


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    base_unit = Column(String(50), nullable=True)
    cost_price = Column(Numeric(15, 2), nullable=False, default=0)
    selling_price = Column(Numeric(15, 2), nullable=False, default=0)
    current_stock = Column(Numeric(15, 3), nullable=False, default=0)
    low_stock_threshold = Column(Numeric(15, 3), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="products")
    stock_movements = relationship("StockMovement", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")
    supplier_order_items = relationship("SupplierOrderItem", back_populates="product")
    units = relationship("ProductUnit", back_populates="product", cascade="all, delete-orphan", order_by="ProductUnit.factor_to_base")


class ProductUnit(Base):
    """A unit in which a product can be stocked or transacted."""

    __tablename__ = "product_units"
    __table_args__ = (UniqueConstraint("product_id", "unit_name", name="uq_product_unit_name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    unit_name = Column(String(50), nullable=False)
    factor_to_base = Column(Numeric(15, 4), nullable=False, default=1)
    is_base = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="units")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    movement_type = Column(Enum(MovementType, values_callable=_enum_values), nullable=False)
    quantity = Column(Numeric(15, 3), nullable=False)
    unit = Column(String(50), nullable=True)
    entered_quantity = Column(Numeric(15, 3), nullable=True)
    reference = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="stock_movements")
