from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from app.models.supplier import Supplier, SupplierOrder, SupplierOrderItem, SupplierOrderStatus
from app.models.inventory import Product, StockMovement, MovementType
from app.schemas.supplier import SupplierCreate, SupplierUpdate, SupplierOrderCreate
from app.services.inventory_service import resolve_unit_factor


def create_supplier(db: Session, user_id: UUID, data: SupplierCreate) -> Supplier:
    supplier = Supplier(user_id=user_id, **data.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(db: Session, supplier_id: UUID, user_id: UUID, data: SupplierUpdate) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.user_id == user_id).first()
    if not supplier:
        raise ValueError("Supplier not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(db: Session, supplier_id: UUID, user_id: UUID) -> None:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.user_id == user_id).first()
    if not supplier:
        raise ValueError("Supplier not found")
    db.delete(supplier)
    db.commit()


def get_suppliers(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    query = db.query(Supplier).filter(Supplier.user_id == user_id)
    total = query.count()
    items = query.order_by(Supplier.name).offset(skip).limit(limit).all()
    return total, items


def create_supplier_order(db: Session, user_id: UUID, data: SupplierOrderCreate) -> SupplierOrder:
    supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id, Supplier.user_id == user_id).first()
    if not supplier:
        raise ValueError("Supplier not found")

    order = SupplierOrder(
        user_id=user_id,
        supplier_id=data.supplier_id,
        status=SupplierOrderStatus.ORDERED,
        total_amount=0,
        notes=data.notes,
        ordered_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()

    total = 0
    for item_data in data.items:
        product = db.query(Product).filter(Product.id == item_data.product_id, Product.user_id == user_id, Product.is_active == True).first()
        if not product:
            raise ValueError(f"Product {item_data.product_id} not found or inactive")
        factor = resolve_unit_factor(db, product, item_data.unit)
        entered_quantity = item_data.quantity
        base_quantity = entered_quantity * factor
        line_total = entered_quantity * item_data.unit_price
        total += line_total
        unit_name = item_data.unit.strip() if item_data.unit and item_data.unit.strip() else (product.base_unit or product.unit)
        item = SupplierOrderItem(
            order_id=order.id,
            product=product,
            quantity=base_quantity,
            unit=unit_name,
            entered_quantity=entered_quantity,
            unit_price=item_data.unit_price,
            total_price=line_total,
        )
        db.add(item)

    order.total_amount = total

    db.commit()
    db.refresh(order)
    return order


def receive_supplier_order(db: Session, order_id: UUID, user_id: UUID) -> SupplierOrder:
    order = (
        db.query(SupplierOrder)
        .options(joinedload(SupplierOrder.items).joinedload(SupplierOrderItem.product))
        .filter(SupplierOrder.id == order_id, SupplierOrder.user_id == user_id)
        .first()
    )
    if not order:
        raise ValueError("Order not found")
    if order.status != SupplierOrderStatus.ORDERED:
        raise ValueError("Only ORDERED orders can be received")

    for item in order.items:
        product = item.product
        if product:
            product.current_stock += item.quantity
            movement = StockMovement(
                product_id=item.product_id,
                user_id=user_id,
                movement_type=MovementType.IN,
                quantity=item.quantity,
                unit=item.unit or (product.base_unit or product.unit),
                entered_quantity=item.entered_quantity if item.entered_quantity is not None else item.quantity,
                reference=f"Supplier Order #{str(order.id)[:8]}",
                notes=f"Received from supplier order",
            )
            db.add(movement)

    order.status = SupplierOrderStatus.RECEIVED
    order.received_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def get_supplier_orders(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    query = db.query(SupplierOrder).filter(SupplierOrder.user_id == user_id)
    total = query.count()
    items = (
        query.order_by(SupplierOrder.created_at.desc())
        .offset(skip)
        .limit(limit)
        .options(joinedload(SupplierOrder.items).joinedload(SupplierOrderItem.product))
        .all()
    )
    return total, items
