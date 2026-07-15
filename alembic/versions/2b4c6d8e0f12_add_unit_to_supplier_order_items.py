"""add entered unit tracking to supplier order items

Revision ID: 2b4c6d8e0f12
Revises: f1a2b3c4d5e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b4c6d8e0f12"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("supplier_order_items")}
    if "unit" not in columns:
        op.add_column("supplier_order_items", sa.Column("unit", sa.String(50), nullable=True))
    if "entered_quantity" not in columns:
        op.add_column("supplier_order_items", sa.Column("entered_quantity", sa.Numeric(15, 3), nullable=True))
    op.execute("UPDATE supplier_order_items SET entered_quantity = quantity WHERE entered_quantity IS NULL")
    op.execute("""
        UPDATE supplier_order_items soi
        SET unit = COALESCE(p.base_unit, p.unit)
        FROM products p
        WHERE soi.product_id = p.id AND soi.unit IS NULL
    """)


def downgrade() -> None:
    op.drop_column("supplier_order_items", "entered_quantity")
    op.drop_column("supplier_order_items", "unit")
