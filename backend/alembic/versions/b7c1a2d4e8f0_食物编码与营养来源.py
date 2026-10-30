"""食物编码与营养来源

Revision ID: b7c1a2d4e8f0
Revises: 44e3579f00ee
Create Date: 2026-10-30 10:20:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c1a2d4e8f0"
down_revision: str | Sequence[str] | None = "44e3579f00ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("foods", sa.Column("food_code", sa.String(length=32), nullable=True))
    op.add_column(
        "foods", sa.Column("nutrient_source", sa.String(length=255), nullable=True)
    )
    op.alter_column(
        "foods",
        "category",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.create_unique_constraint(op.f("uq_foods_food_code"), "foods", ["food_code"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_foods_food_code"), "foods", type_="unique")
    op.alter_column(
        "foods",
        "category",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.drop_column("foods", "nutrient_source")
    op.drop_column("foods", "food_code")
