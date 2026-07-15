"""add product units and unit of measure conversion

Revision ID: c7e1a2b3d4f5
Revises: 11d9795f8da6
Create Date: 2026-06-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7e1a2b3d4f5"
down_revision: Union[str, None] = "11d9795f8da6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "base_unit" not in product_columns:
        op.add_column("products", sa.Column("base_unit", sa.String(50), nullable=True))
    op.execute("UPDATE products SET base_unit = unit WHERE base_unit IS NULL")

    movement_columns = {column["name"] for column in inspector.get_columns("stock_movements")}
    if "unit" not in movement_columns:
        op.add_column("stock_movements", sa.Column("unit", sa.String(50), nullable=True))
    if "entered_quantity" not in movement_columns:
        op.add_column("stock_movements", sa.Column("entered_quantity", sa.Numeric(15, 3), nullable=True))

    if not inspector.has_table("product_units"):
        op.create_table(
            "product_units",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("unit_name", sa.String(50), nullable=False),
            sa.Column("factor_to_base", sa.Numeric(15, 4), nullable=False, server_default="1"),
            sa.Column("is_base", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("product_id", "unit_name", name="uq_product_unit_name"),
        )

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        INSERT INTO product_units (id, product_id, user_id, unit_name, factor_to_base, is_base, created_at)
        SELECT gen_random_uuid(), p.id, p.user_id, COALESCE(p.base_unit, p.unit), 1, true, now()
        FROM products p
        WHERE COALESCE(p.base_unit, p.unit) IS NOT NULL
          AND TRIM(COALESCE(p.base_unit, p.unit)) <> ''
        """
    )


def downgrade() -> None:
    op.drop_table("product_units")
    op.drop_column("stock_movements", "entered_quantity")
    op.drop_column("stock_movements", "unit")
    op.drop_column("products", "base_unit")
