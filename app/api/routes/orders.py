import re
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from io import BytesIO
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User, UserRole
from app.models.order import BuyerOrder, BuyerOrderStatus, OrderItem
from app.schemas.order import BuyerOrderCreate, BuyerOrderOut, BuyerOrderList
from app.services import order_service
from app.services.invoice_service import generate_invoice_pdf, get_invoice_data

router = APIRouter(prefix="/orders", tags=["Buyer Orders"])


@router.get("", response_model=BuyerOrderList)
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = order_service.get_buyer_orders(db, current_user.id, skip=skip, limit=limit)
    return BuyerOrderList(total=total, items=items)


@router.post("", response_model=BuyerOrderOut, status_code=201)
def create_order(
    data: BuyerOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return order_service.create_buyer_order(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/customers/search")
def search_customers(
    phone: str = Query(..., min_length=3, max_length=10, pattern=r"^\d+$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find this business's existing buyers by the digits typed so far."""
    digits = re.sub(r"\D", "", phone)
    normalized_order_phone = func.right(func.regexp_replace(BuyerOrder.buyer_phone, r"\D", "", "g"), 10)
    previous_buyers = (
        db.query(BuyerOrder)
        .filter(
            BuyerOrder.user_id == current_user.id,
            BuyerOrder.buyer_phone.isnot(None),
            normalized_order_phone.like(f"{digits}%"),
        )
        .order_by(BuyerOrder.created_at.desc())
        .limit(50)
        .all()
    )

    items = []
    seen_phones = set()
    for order in previous_buyers:
        normalized = re.sub(r"\D", "", order.buyer_phone or "")[-10:]
        if len(normalized) != 10 or normalized in seen_phones:
            continue
        seen_phones.add(normalized)
        items.append({
            "id": str(order.id),
            "name": order.buyer_name or "Unnamed customer",
            "phone_number": normalized,
        })

    # Registered customer accounts are also valid customers, but are only a
    # fallback because buyer orders are scoped to the signed-in business.
    normalized_user_phone = func.right(func.regexp_replace(User.phone_number, r"\D", "", "g"), 10)
    registered_customers = (
        db.query(User)
        .filter(
            User.role == UserRole.CUSTOMER,
            User.is_active == True,
            normalized_user_phone.like(f"{digits}%"),
        )
        .order_by(User.business_name.asc(), User.phone_number.asc())
        .limit(20)
        .all()
    )

    for customer in registered_customers:
        normalized = re.sub(r"\D", "", customer.phone_number or "")[-10:]
        if len(normalized) != 10 or normalized in seen_phones or len(items) >= 10:
            continue
        seen_phones.add(normalized)
        items.append({
            "id": str(customer.id),
            "name": customer.business_name or "Unnamed customer",
            "phone_number": normalized,
        })

    return {
        "items": items[:10],
    }


@router.get("/customers/item-history")
def customer_item_history(
    phone: str = Query(..., min_length=10, max_length=10, pattern=r"^\d+$"),
    product_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the two most recent non-cancelled orders for this customer and item."""
    digits = re.sub(r"\D", "", phone)
    normalized_order_phone = func.right(func.regexp_replace(BuyerOrder.buyer_phone, r"\D", "", "g"), 10)
    history = (
        db.query(BuyerOrder, OrderItem)
        .join(OrderItem, OrderItem.order_id == BuyerOrder.id)
        .filter(
            BuyerOrder.user_id == current_user.id,
            BuyerOrder.status != BuyerOrderStatus.CANCELLED,
            BuyerOrder.buyer_phone.isnot(None),
            normalized_order_phone == digits,
            OrderItem.product_id == product_id,
        )
        .order_by(BuyerOrder.created_at.desc())
        .limit(2)
        .all()
    )
    return {
        "items": [
            {
                "order_id": str(order.id),
                "order_date": order.created_at.isoformat(),
                "quantity": item.entered_quantity if item.entered_quantity is not None else item.quantity,
                "unit": item.unit,
                "unit_price": item.unit_price,
            }
            for order, item in history
        ]
    }


@router.put("/{order_id}", response_model=BuyerOrderOut)
def update_order(
    order_id: UUID,
    data: BuyerOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return order_service.update_buyer_order(db, order_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{order_id}", response_model=BuyerOrderOut)
def get_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return order_service.get_buyer_order(db, order_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{order_id}/checkout", response_model=BuyerOrderOut)
def checkout(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return order_service.checkout_order(db, order_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{order_id}/cancel", response_model=BuyerOrderOut)
def cancel(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return order_service.cancel_order(db, order_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{order_id}/invoice")
def download_invoice(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download invoice PDF for a completed order."""
    try:
        pdf_bytes = generate_invoice_pdf(db, order_id, current_user.id)
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=invoice_{order_id}.pdf"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate invoice: {str(e)}")


@router.get("/{order_id}/invoice-data")
def invoice_data(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return invoice data for preview, print, and WhatsApp sharing."""
    try:
        return get_invoice_data(db, order_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invoice data: {str(e)}")
