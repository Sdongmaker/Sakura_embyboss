"""drop points and security code columns

Revision ID: 20260917_04
Revises: 20260916_03
Create Date: 2026-09-17 04:00:00
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260917_04"
down_revision = "20260916_03"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    """
    移除安全码(emby.pwd2 / emby2.pwd2)、积分体系(emby.iv)与求片计费字段(request_records.cost)。
    积分与安全码功能已从代码中整体删除，这里同步清理历史列。
    """
    for table, column in (("emby", "pwd2"), ("emby", "iv"), ("emby2", "pwd2"), ("request_records", "cost")):
        if _has_column(table, column):
            op.drop_column(table, column)


def downgrade() -> None:
    for table, column, column_type in (
        ("emby", "pwd2", sa.String(length=255)),
        ("emby", "iv", sa.Integer()),
        ("emby2", "pwd2", sa.String(length=255)),
        ("request_records", "cost", sa.String(length=255)),
    ):
        if not _has_column(table, column):
            op.add_column(table, sa.Column(column, column_type, nullable=True))
