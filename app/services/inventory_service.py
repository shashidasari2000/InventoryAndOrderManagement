from sqlalchemy import func
from sqlalchemy.orm import Session
from uuid import UUID
from decimal import Decimal
from typing import Optional
from app.models.inventory import Product, ProductUnit, StockMovement, MovementType
from app.schemas.inventory import ProductCreate, ProductUpdate, ProductUnitCreate, StockMovementCreate


def _generate_sku(db: Session, user_id: UUID) -> str:
    """Generate unique SKU: PRD-XXXXX format based on user's product count."""
    count = db.query(Product).filter(Product.user_id == user_id).count()
    return f"PRD-{count + 1:05d}"


def _ensure_base_unit(db: Session, product: Product) -> None:
    base_name = (product.base_unit or product.unit or "").strip()
    if not base_name:
        return

    product.base_unit = base_name
    if not (product.unit or "").strip():
        product.unit = base_name

    db.query(ProductUnit).filter(ProductUnit.product_id == product.id).update(
        {ProductUnit.is_base: False}, synchronize_session=False
    )
    existing = (
        db.query(ProductUnit)
        .filter(
            ProductUnit.product_id == product.id,
            func.lower(ProductUnit.unit_name) == base_name.lower(),
        )
        .first()
    )
    if existing:
        existing.factor_to_base = Decimal("1")
        existing.is_base = True
    else:
        db.add(ProductUnit(
            product_id=product.id,
            user_id=product.user_id,
            unit_name=base_name,
            factor_to_base=Decimal("1"),
            is_base=True,
        ))


def create_product(db: Session, user_id: UUID, data: ProductCreate) -> Product:
    product_data = data.model_dump(exclude={"units"})
    extra_units = data.units or []
    # Auto-generate SKU if not provided
    if not product_data.get("sku"):
        product_data["sku"] = _generate_sku(db, user_id)
    if not product_data.get("base_unit"):
        product_data["base_unit"] = product_data.get("unit")
    if product_data.get("base_unit") and not product_data.get("unit"):
        product_data["unit"] = product_data["base_unit"]
    product = Product(user_id=user_id, **product_data)
    db.add(product)
    db.flush()
    _ensure_base_unit(db, product)

    base_name = (product.base_unit or product.unit or "").strip().lower()
    seen_names: set[str] = set()
    for unit in extra_units:
        name = unit.unit_name.strip()
        if not name or name.lower() == base_name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        db.add(ProductUnit(
            product_id=product.id,
            user_id=user_id,
            unit_name=name,
            factor_to_base=unit.factor_to_base,
            is_base=False,
        ))
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, product_id: UUID, user_id: UUID, data: ProductUpdate) -> Product:
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user_id).first()
    if not product:
        raise ValueError("Product not found")
    fields = data.model_dump(exclude_none=True)
    if "base_unit" in fields and fields["base_unit"]:
        fields["base_unit"] = fields["base_unit"].strip()
        if not fields.get("unit"):
            fields["unit"] = fields["base_unit"]
    for field, value in fields.items():
        setattr(product, field, value)
    if "base_unit" in fields or "unit" in fields:
        _ensure_base_unit(db, product)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: UUID, user_id: UUID) -> None:
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user_id, Product.is_active == True).first()
    if not product:
        raise ValueError("Product not found")
    product.is_active = False
    db.commit()


def get_products(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    query = db.query(Product).filter(Product.user_id == user_id, Product.is_active == True)
    total = query.count()
    items = query.order_by(Product.name).offset(skip).limit(limit).all()
    return total, items


def get_product(db: Session, product_id: UUID, user_id: UUID) -> Product:
    product = db.query(Product).filter(Product.id == product_id, Product.user_id == user_id, Product.is_active == True).first()
    if not product:
        raise ValueError("Product not found")
    return product


def resolve_unit_factor(db: Session, product: Product, unit_name: Optional[str]) -> Decimal:
    if not unit_name or not unit_name.strip():
        return Decimal("1")
    name = unit_name.strip()
    base_name = (product.base_unit or product.unit or "").strip()
    if base_name and name.lower() == base_name.lower():
        return Decimal("1")
    unit = (
        db.query(ProductUnit)
        .filter(
            ProductUnit.product_id == product.id,
            func.lower(ProductUnit.unit_name) == name.lower(),
        )
        .first()
    )
    if not unit:
        raise ValueError(f"Unknown unit '{unit_name}' for product '{product.name}'")
    return Decimal(unit.factor_to_base)


def record_stock_movement(db: Session, user_id: UUID, data: StockMovementCreate) -> StockMovement:
    product = db.query(Product).filter(Product.id == data.product_id, Product.user_id == user_id, Product.is_active == True).first()
    if not product:
        raise ValueError("Product not found or inactive")

    factor = resolve_unit_factor(db, product, data.unit)
    base_quantity = data.quantity * factor

    if data.movement_type == MovementType.IN:
        product.current_stock += base_quantity
    elif data.movement_type == MovementType.OUT:
        if product.current_stock < base_quantity:
            raise ValueError(f"Insufficient stock. Available: {product.current_stock} {product.base_unit or product.unit or ''}".strip())
        product.current_stock -= base_quantity
    else:
        product.current_stock += base_quantity

    movement = StockMovement(
        product_id=data.product_id,
        user_id=user_id,
        movement_type=data.movement_type,
        quantity=base_quantity,
        unit=data.unit.strip() if data.unit and data.unit.strip() else (product.base_unit or product.unit),
        entered_quantity=data.quantity,
        reference=data.reference,
        notes=data.notes,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


def list_product_units(db: Session, product_id: UUID, user_id: UUID) -> list[ProductUnit]:
    product = get_product(db, product_id, user_id)
    return list(product.units)


def add_product_unit(db: Session, product_id: UUID, user_id: UUID, data: ProductUnitCreate) -> ProductUnit:
    product = get_product(db, product_id, user_id)
    name = data.unit_name.strip()
    existing = db.query(ProductUnit).filter(
        ProductUnit.product_id == product.id,
        func.lower(ProductUnit.unit_name) == name.lower(),
    ).first()
    if existing:
        raise ValueError(f"Unit '{name}' already exists for this product")
    if data.is_base:
        product.base_unit = name
        product.unit = name
        _ensure_base_unit(db, product)
        db.commit()
        db.refresh(product)
        return next(u for u in product.units if u.is_base)
    unit = ProductUnit(
        product_id=product.id,
        user_id=user_id,
        unit_name=name,
        factor_to_base=data.factor_to_base,
        is_base=False,
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def update_product_unit(db: Session, product_id: UUID, unit_id: UUID, user_id: UUID, data: ProductUnitCreate) -> ProductUnit:
    unit = db.query(ProductUnit).filter(
        ProductUnit.id == unit_id,
        ProductUnit.product_id == product_id,
        ProductUnit.user_id == user_id,
    ).first()
    if not unit:
        raise ValueError("Unit not found")
    duplicate = db.query(ProductUnit).filter(
        ProductUnit.product_id == product_id,
        ProductUnit.id != unit_id,
        func.lower(ProductUnit.unit_name) == data.unit_name.strip().lower(),
    ).first()
    if duplicate:
        raise ValueError(f"Unit '{data.unit_name.strip()}' already exists for this product")
    if unit.is_base and not data.is_base:
        raise ValueError("The base unit must remain the base unit")
    unit.unit_name = data.unit_name.strip()
    unit.factor_to_base = Decimal("1") if unit.is_base else data.factor_to_base
    db.commit()
    db.refresh(unit)
    return unit


def delete_product_unit(db: Session, product_id: UUID, unit_id: UUID, user_id: UUID) -> None:
    unit = db.query(ProductUnit).filter(
        ProductUnit.id == unit_id,
        ProductUnit.product_id == product_id,
        ProductUnit.user_id == user_id,
    ).first()
    if not unit:
        raise ValueError("Unit not found")
    if unit.is_base:
        raise ValueError("Cannot delete the base unit")
    db.delete(unit)
    db.commit()


def get_stock_movements(db: Session, user_id: UUID, product_id: Optional[UUID] = None, skip: int = 0, limit: int = 50):
    query = db.query(StockMovement).filter(StockMovement.user_id == user_id)
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    total = query.count()
    items = query.order_by(StockMovement.created_at.desc()).offset(skip).limit(limit).all()
    return total, items
