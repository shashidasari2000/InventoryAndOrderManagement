from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
import csv
import io
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.inventory import (
    ProductCreate,
    ProductUpdate,
    ProductOut,
    ProductList,
    ProductUnitCreate,
    ProductUnitOut,
    StockMovementCreate,
    StockMovementOut,
)
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/products", response_model=ProductList)
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = inventory_service.get_products(db, current_user.id, skip=skip, limit=limit)
    return ProductList(total=total, items=items)


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return inventory_service.create_product(db, current_user.id, data)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.get_product(db, product_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.update_product(db, product_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        inventory_service.delete_product(db, product_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/products/{product_id}/units", response_model=list[ProductUnitOut])
def list_product_units(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.list_product_units(db, product_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/products/{product_id}/units", response_model=ProductUnitOut, status_code=201)
def add_product_unit(
    product_id: UUID,
    data: ProductUnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.add_product_unit(db, product_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.put("/products/{product_id}/units/{unit_id}", response_model=ProductUnitOut)
def update_product_unit(
    product_id: UUID,
    unit_id: UUID,
    data: ProductUnitCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.update_product_unit(db, product_id, unit_id, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/products/{product_id}/units/{unit_id}", status_code=204)
def delete_product_unit(
    product_id: UUID,
    unit_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        inventory_service.delete_product_unit(db, product_id, unit_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/stock-movements", response_model=StockMovementOut, status_code=201)
def record_movement(
    data: StockMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return inventory_service.record_stock_movement(db, current_user.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/stock-movements", response_model=dict)
def list_movements(
    product_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = inventory_service.get_stock_movements(db, current_user.id, product_id=product_id, skip=skip, limit=limit)
    return {"total": total, "items": [StockMovementOut.model_validate(i).model_dump() for i in items]}


@router.post("/products/import", response_model=dict)
def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import products from CSV file.
    Expected columns: name, sku, unit, cost_price, selling_price, current_stock, low_stock_threshold, description
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
                # Build product data
                product_data = {
                    "name": row.get("name", "").strip(),
                    "sku": row.get("sku", "").strip() or None,
                    "unit": row.get("unit", "").strip() or None,
                    "cost_price": float(row.get("cost_price", 0) or 0),
                    "selling_price": float(row.get("selling_price", 0) or 0),
                    "current_stock": float(row.get("current_stock", 0) or 0),
                    "low_stock_threshold": float(row.get("low_stock_threshold", 0) or 0) if row.get("low_stock_threshold") else None,
                    "description": row.get("description", "").strip() or None,
                }

                if not product_data["name"]:
                    errors.append(f"Row {row_num}: Missing product name")
                    continue

                data = ProductCreate(**product_data)
                inventory_service.create_product(db, current_user.id, data)
                created += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        return {
            "imported": created,
            "errors": errors,
            "message": f"Successfully imported {created} products" if created else "No products imported"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")
