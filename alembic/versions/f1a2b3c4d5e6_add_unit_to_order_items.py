"""add entered unit tracking to buyer order items

Revision ID: f1a2b3c4d5e6
Revises: c7e1a2b3d4f5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "c7e1a2b3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("order_items")}
    if "unit" not in columns:
        op.add_column("order_items", sa.Column("unit", sa.String(50), nullable=True))
    if "entered_quantity" not in columns:
        op.add_column("order_items", sa.Column("entered_quantity", sa.Numeric(15, 3), nullable=True))
    op.execute("UPDATE order_items SET entered_quantity = quantity WHERE entered_quantity IS NULL")
    op.execute("""
        UPDATE order_items oi
        SET unit = COALESCE(p.base_unit, p.unit)
        FROM products p
        WHERE oi.product_id = p.id AND oi.unit IS NULL
    """)


def downgrade() -> None:
    op.drop_column("order_items", "entered_quantity")
    op.drop_column("order_items", "unit")
