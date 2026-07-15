from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.order import BuyerOrder, OrderItem, BuyerOrderStatus
from app.models.inventory import Product, StockMovement, MovementType
from app.schemas.order import BuyerOrderCreate
from app.services.inventory_service import resolve_unit_factor


def create_buyer_order(db: Session, user_id: UUID, data: BuyerOrderCreate) -> BuyerOrder:
    order = BuyerOrder(
        user_id=user_id,
        buyer_name=data.buyer_name,
        buyer_phone=data.buyer_phone,
        status=BuyerOrderStatus.DRAFT,
        subtotal=0,
        discount=data.discount,
        total_amount=0,
        notes=data.notes,
    )
    db.add(order)
    db.flush()

    subtotal = Decimal("0")
    for item_data in data.items:
        product = db.query(Product).filter(Product.id == item_data.product_id, Product.user_id == user_id, Product.is_active == True).first()
        if not product:
            raise ValueError(f"Product {item_data.product_id} not found or inactive")
        factor = resolve_unit_factor(db, product, item_data.unit)
        entered_quantity = item_data.quantity
        base_quantity = entered_quantity * factor
        line_total = entered_quantity * item_data.unit_price
        subtotal += line_total
        unit_name = item_data.unit.strip() if item_data.unit and item_data.unit.strip() else (product.base_unit or product.unit)
        item = OrderItem(
            order_id=order.id,
            product=product,
            quantity=base_quantity,
            unit=unit_name,
            entered_quantity=entered_quantity,
            unit_price=item_data.unit_price,
            cost_price_snapshot=product.cost_price,
            total_price=line_total,
        )
        db.add(item)

    order.subtotal = subtotal
    order.total_amount = subtotal - data.discount

    db.commit()
    db.refresh(order)
    return order


def update_buyer_order(db: Session, order_id: UUID, user_id: UUID, data: BuyerOrderCreate) -> BuyerOrder:
    order = _load_order_with_items(db, order_id, user_id)
    if not order:
        raise ValueError("Order not found")
    if order.status != BuyerOrderStatus.DRAFT:
        raise ValueError("Only DRAFT orders can be edited")

    subtotal = Decimal("0")
    updated_items: list[OrderItem] = []
    for item_data in data.items:
        product = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.user_id == user_id,
            Product.is_active == True,
        ).first()
        if not product:
            raise ValueError(f"Product {item_data.product_id} not found or inactive")
        factor = resolve_unit_factor(db, product, item_data.unit)
        entered_quantity = item_data.quantity
        base_quantity = entered_quantity * factor
        line_total = entered_quantity * item_data.unit_price
        subtotal += line_total
        updated_items.append(OrderItem(
            product=product,
            quantity=base_quantity,
            unit=item_data.unit.strip() if item_data.unit and item_data.unit.strip() else (product.base_unit or product.unit),
            entered_quantity=entered_quantity,
            unit_price=item_data.unit_price,
            cost_price_snapshot=product.cost_price,
            total_price=line_total,
        ))

    order.buyer_name = data.buyer_name
    order.buyer_phone = data.buyer_phone
    order.discount = data.discount
    order.notes = data.notes
    order.subtotal = subtotal
    order.total_amount = subtotal - data.discount
    order.items.clear()
    db.flush()
    for item in updated_items:
        order.items.append(item)
    db.commit()
    db.refresh(order)
    return order


def _load_order_with_items(db: Session, order_id: UUID, user_id: UUID) -> BuyerOrder | None:
    return (
        db.query(BuyerOrder)
        .options(joinedload(BuyerOrder.items).joinedload(OrderItem.product))
        .filter(BuyerOrder.id == order_id, BuyerOrder.user_id == user_id)
        .first()
    )


def checkout_order(db: Session, order_id: UUID, user_id: UUID) -> BuyerOrder:
    order = _load_order_with_items(db, order_id, user_id)
    if not order:
        raise ValueError("Order not found")
    if order.status != BuyerOrderStatus.DRAFT:
        raise ValueError("Only DRAFT orders can be checked out")

    for item in order.items:
        product = item.product
        if not product:
            raise ValueError(f"Product {item.product_id} not found")
        if product.current_stock < item.quantity:
            raise ValueError(f"Insufficient stock for '{product.name}'. Available: {product.current_stock}, Required: {item.quantity}")
        product.current_stock -= item.quantity
        movement = StockMovement(
            product_id=item.product_id,
            user_id=user_id,
            movement_type=MovementType.OUT,
            quantity=item.quantity,
            unit=item.unit or (product.base_unit or product.unit),
            entered_quantity=item.entered_quantity if item.entered_quantity is not None else item.quantity,
            reference=f"Buyer Order #{str(order.id)[:8]}",
            notes=f"Sold to {order.buyer_name or 'customer'}",
        )
        db.add(movement)

    order.status = BuyerOrderStatus.CONFIRMED
    order.checked_out_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: UUID, user_id: UUID) -> BuyerOrder:
    order = _load_order_with_items(db, order_id, user_id)
    if not order:
        raise ValueError("Order not found")
    if order.status != BuyerOrderStatus.DRAFT:
        raise ValueError("Only DRAFT orders can be cancelled")
    order.status = BuyerOrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    return order


def get_buyer_orders(db: Session, user_id: UUID, skip: int = 0, limit: int = 50):
    query = db.query(BuyerOrder).filter(BuyerOrder.user_id == user_id)
    total = query.count()
    items = (
        query.order_by(BuyerOrder.created_at.desc())
        .offset(skip)
        .limit(limit)
        .options(joinedload(BuyerOrder.items).joinedload(OrderItem.product))
        .all()
    )
    return total, items


def get_buyer_order(db: Session, order_id: UUID, user_id: UUID) -> BuyerOrder:
    order = _load_order_with_items(db, order_id, user_id)
    if not order:
        raise ValueError("Order not found")
    return order
