"""create shop_orders reconciliation table

Revision ID: 20260919_05
Revises: 20260917_04
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_05"
down_revision = "20260917_04"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "shop_orders" not in _tables(bind):
        op.create_table(
            "shop_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_no", sa.String(32), nullable=False),
            sa.Column("downstream_order_no", sa.String(64), nullable=False),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("sku_code", sa.String(32), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tg", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("embyid", sa.String(255), nullable=True),
            sa.Column("emby_name", sa.String(255), nullable=True),
            sa.Column("ex_before", sa.DateTime(), nullable=True),
            sa.Column("ex_after", sa.DateTime(), nullable=True),
            sa.Column("lv_before", sa.String(1), nullable=True),
            sa.Column("lv_after", sa.String(1), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
            sa.Column("error_message", sa.String(255), nullable=True),
            sa.Column("created_account", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notify_state", sa.String(16), nullable=False, server_default="skipped"),
            sa.Column("replayed_from", sa.Integer(), nullable=True),
            sa.Column("operation_stage", sa.String(32), nullable=False, server_default="prepared"),
            sa.Column("server_results", sa.Text(), nullable=True),
            sa.Column("account_password", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_no"),
            sa.UniqueConstraint("downstream_order_no"),
            sa.Index("ix_shop_orders_tg", "tg"),
            sa.Index("ix_shop_orders_status", "status"),
            sa.Index("ix_shop_orders_created_at", "created_at"),
        )
    else:
        # Allow a partially applied deployment to catch up without rebuilding.
        columns = _columns(bind, "shop_orders")
        for name, column in (
            ("operation_stage", sa.Column("operation_stage", sa.String(32), nullable=False, server_default="prepared")),
            ("server_results", sa.Column("server_results", sa.Text(), nullable=True)),
            ("account_password", sa.Column("account_password", sa.String(255), nullable=True)),
        ):
            if name not in columns:
                op.add_column("shop_orders", column)
    if "emby" in _tables(bind) and "us" in _columns(bind, "emby"):
        op.drop_column("emby", "us")
    for table in ("partition_grants", "partition_codes"):
        if table in _tables(bind):
            op.drop_table(table)


def downgrade() -> None:
    if "shop_orders" in _tables(op.get_bind()):
        op.drop_table("shop_orders")
