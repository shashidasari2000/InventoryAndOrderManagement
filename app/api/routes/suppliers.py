from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
import csv
import io
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.supplier import (
    SupplierCreate, SupplierUpdate, SupplierOut, SupplierList,
    SupplierOrderCreate, SupplierOrderOut,
)
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get("", response_model=SupplierList)
def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = supplier_service.get_suppliers(db, current_user.id, skip=skip, limit=limit)
    return SupplierList(total=total, items=items)


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return supplier_service.create_supplier(db, current_user.id, data)


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: UUID,
    data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return supplier_service.update_supplier(db, supplier_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        supplier_service.delete_supplier(db, supplier_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/orders", response_model=dict)
def list_supplier_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = supplier_service.get_supplier_orders(db, current_user.id, skip=skip, limit=limit)
    return {"total": total, "items": [SupplierOrderOut.model_validate(i).model_dump() for i in items]}


@router.post("/orders", response_model=SupplierOrderOut, status_code=201)
def create_supplier_order(
    data: SupplierOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return supplier_service.create_supplier_order(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/orders/{order_id}/receive", response_model=SupplierOrderOut)
def receive_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return supplier_service.receive_supplier_order(db, order_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/import", response_model=dict)
def import_suppliers_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import suppliers from CSV file.
    Expected columns: name, contact_name, phone, email, address, gst_number, notes
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        content = file.file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))

        created = 0
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):
            try:
                # Build supplier data
                supplier_data = {
                    "name": row.get("name", "").strip(),
                    "contact_name": row.get("contact_name", "").strip() or None,
                    "phone": row.get("phone", "").strip() or None,
                    "email": row.get("email", "").strip() or None,
                    "address": row.get("address", "").strip() or None,
                    "gst_number": row.get("gst_number", "").strip() or None,
                    "notes": row.get("notes", "").strip() or None,
                }

                if not supplier_data["name"]:
                    errors.append(f"Row {row_num}: Missing supplier name")
                    continue

                data = SupplierCreate(**supplier_data)
                supplier_service.create_supplier(db, current_user.id, data)
                created += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return {
            "imported": created,
            "errors": errors,
            "message": f"Successfully imported {created} suppliers" if created else "No suppliers imported"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")
