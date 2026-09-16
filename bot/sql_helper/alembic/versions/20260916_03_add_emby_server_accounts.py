"""add emby_server_accounts

Revision ID: 20260916_03
Revises: 20260315_02
Create Date: 2026-09-16 10:00:00
"""

import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260916_03"
down_revision = "20260315_02"
branch_labels = None
depends_on = None


def _primary_server_name() -> str:
    """
    读取 config.json 中 servers[0].name 作为回填用的主服标识，读不到则退回 main
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("servers") or []
        if servers and servers[0].get("name"):
            return str(servers[0]["name"])[:32]
    except Exception:
        pass
    return "main"


def _table_names(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "emby_server_accounts" not in _table_names(bind):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS `emby_server_accounts` (
              `tg` BIGINT NOT NULL,
              `server` VARCHAR(32) NOT NULL,
              `embyid` VARCHAR(255) NULL,
              `name` VARCHAR(255) NULL,
              `status` VARCHAR(16) NULL DEFAULT 'active',
              `cr` DATETIME NULL,
              PRIMARY KEY (`tg`, `server`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
        )

    # 存量单服数据回填：已有 embyid 的账户默认挂在主服下
    op.execute(
        sa.text(
            """
            INSERT IGNORE INTO `emby_server_accounts` (`tg`, `server`, `embyid`, `name`, `status`, `cr`)
            SELECT `tg`, :server, `embyid`, `name`, 'active', `cr`
            FROM `emby`
            WHERE `embyid` IS NOT NULL AND `embyid` <> ''
            """
        ).bindparams(server=_primary_server_name())
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "emby_server_accounts" in _table_names(bind):
        op.drop_table("emby_server_accounts")
