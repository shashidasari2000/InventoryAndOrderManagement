from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.inventory import MovementType


class ProductUnitBase(BaseModel):
    unit_name: str
    factor_to_base: Decimal = Decimal("1")
    is_base: bool = False

    @field_validator("unit_name")
    @classmethod
    def unit_name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Unit name is required")
        return v.strip()

    @field_validator("factor_to_base")
    @classmethod
    def factor_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Conversion factor must be greater than 0")
        return v


class ProductUnitCreate(ProductUnitBase):
    pass


class ProductUnitOut(BaseModel):
    id: UUID
    product_id: UUID
    unit_name: str
    factor_to_base: Decimal
    is_base: bool

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    sku: Optional[str] = None
    unit: Optional[str] = None
    base_unit: Optional[str] = None
    cost_price: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    current_stock: Decimal = Decimal("0")
    low_stock_threshold: Optional[Decimal] = None
    description: Optional[str] = None
    units: Optional[List[ProductUnitCreate]] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Product name is required")
        return v.strip()


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    unit: Optional[str] = None
    base_unit: Optional[str] = None
    cost_price: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None
    low_stock_threshold: Optional[Decimal] = None
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Product name cannot be empty")
        return v.strip() if v else v


class ProductOut(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    sku: Optional[str]
    unit: Optional[str]
    base_unit: Optional[str]
    cost_price: Decimal
    selling_price: Decimal
    current_stock: Decimal
    low_stock_threshold: Optional[Decimal]
    description: Optional[str]
    is_active: bool
    units: List[ProductUnitOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StockMovementCreate(BaseModel):
    product_id: UUID
    movement_type: MovementType
    quantity: Decimal
    unit: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class StockMovementOut(BaseModel):
    id: UUID
    product_id: UUID
    user_id: UUID
    movement_type: MovementType
    quantity: Decimal
    unit: Optional[str]
    entered_quantity: Optional[Decimal]
    reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ProductList(BaseModel):
    total: int
    items: List[ProductOut]
