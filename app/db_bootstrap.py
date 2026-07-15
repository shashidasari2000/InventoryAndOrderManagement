import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import Base
from app.models.inventory import ProductUnit  # noqa: F401


def _add_column_if_missing(engine: Engine, table_name: str, column_name: str, definition: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def ensure_inventory_uom_schema(engine: Engine) -> None:
    """Patch databases created by the historical create_all-only startup path."""
    _add_column_if_missing(engine, "products", "base_unit", "VARCHAR(50)")
    _add_column_if_missing(engine, "stock_movements", "unit", "VARCHAR(50)")
    _add_column_if_missing(engine, "stock_movements", "entered_quantity", "NUMERIC(15, 3)")
    _add_column_if_missing(engine, "order_items", "unit", "VARCHAR(50)")
    _add_column_if_missing(engine, "order_items", "entered_quantity", "NUMERIC(15, 3)")
    _add_column_if_missing(engine, "supplier_order_items", "unit", "VARCHAR(50)")
    _add_column_if_missing(engine, "supplier_order_items", "entered_quantity", "NUMERIC(15, 3)")

    with engine.begin() as connection:
        if inspect(engine).has_table("products"):
            connection.execute(text("UPDATE products SET base_unit = unit WHERE base_unit IS NULL"))
            for table_name in ("order_items", "supplier_order_items"):
                if inspect(engine).has_table(table_name):
                    connection.execute(text(f"UPDATE {table_name} SET entered_quantity = quantity WHERE entered_quantity IS NULL"))
                    connection.execute(text(f"""
                        UPDATE {table_name} item
                        SET unit = (SELECT COALESCE(products.base_unit, products.unit) FROM products WHERE products.id = item.product_id)
                        WHERE item.unit IS NULL
                    """))

    Base.metadata.tables["product_units"].create(bind=engine, checkfirst=True)
    _seed_missing_base_units(engine)


def _seed_missing_base_units(engine: Engine) -> None:
    if not inspect(engine).has_table("products"):
        return

    with engine.begin() as connection:
        rows = connection.execute(text("""
            SELECT id, user_id, COALESCE(base_unit, unit) AS unit_name
            FROM products
            WHERE COALESCE(base_unit, unit) IS NOT NULL
              AND TRIM(COALESCE(base_unit, unit)) <> ''
        """)).mappings().all()
        for row in rows:
            existing = connection.execute(text("""
                SELECT 1 FROM product_units
                WHERE product_id = :product_id
                  AND LOWER(unit_name) = LOWER(:unit_name)
                LIMIT 1
            """), {"product_id": row["id"], "unit_name": row["unit_name"]}).first()
            if existing:
                continue
            connection.execute(text("""
                INSERT INTO product_units
                    (id, product_id, user_id, unit_name, factor_to_base, is_base, created_at)
                VALUES
                    (:id, :product_id, :user_id, :unit_name, 1, true, CURRENT_TIMESTAMP)
            """), {
                "id": str(uuid.uuid4()),
                "product_id": row["id"],
                "user_id": row["user_id"],
                "unit_name": row["unit_name"],
            })
