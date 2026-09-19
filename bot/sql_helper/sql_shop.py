"""Persistent shop order ledger and idempotent SQL helpers."""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text, or_
from sqlalchemy.exc import IntegrityError

from bot import LOGGER
from bot.sql_helper import Base, Session


class ShopOrder(Base):
    __tablename__ = "shop_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(32), unique=True, nullable=False)
    downstream_order_no = Column(String(64), unique=True, nullable=False)
    trace_id = Column(String(64), nullable=True)
    sku_code = Column(String(32), nullable=False, default="INVALID")
    quantity = Column(Integer, nullable=False, default=1)
    days = Column(Integer, nullable=False, default=0)
    tg = Column(BigInteger, nullable=False, default=0)
    embyid = Column(String(255), nullable=True)
    emby_name = Column(String(255), nullable=True)
    ex_before = Column(DateTime, nullable=True)
    ex_after = Column(DateTime, nullable=True)
    lv_before = Column(String(1), nullable=True)
    lv_after = Column(String(1), nullable=True)
    status = Column(String(24), nullable=False, default="processing")
    error_message = Column(String(255), nullable=True)
    created_account = Column(Integer, nullable=False, default=0)
    notify_state = Column(String(16), nullable=False, default="skipped")
    replayed_from = Column(Integer, nullable=True)
    # Durable recovery markers.  Credentials are never exposed by HTTP; the
    # password is retained only so a crash after remote creation can be resumed.
    operation_stage = Column(String(32), nullable=False, default="prepared")
    server_results = Column(Text, nullable=True)
    account_password = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_shop_orders_tg", "tg"),
        Index("ix_shop_orders_status", "status"),
        Index("ix_shop_orders_created_at", "created_at"),
    )


def _reload(session, order_id: int) -> Optional[ShopOrder]:
    return session.query(ShopOrder).filter(ShopOrder.id == int(order_id)).first()


def sql_create_shop_order(**values) -> tuple[Optional[ShopOrder], bool]:
    """Insert an order; a unique-key race returns the existing winner."""
    with Session() as session:
        try:
            row = ShopOrder(**values)
            session.add(row)
            session.commit()
            return row, True
        except IntegrityError:
            session.rollback()
            downstream = values.get("downstream_order_no")
            if not downstream:
                return None, False
            return session.query(ShopOrder).filter(
                ShopOrder.downstream_order_no == downstream
            ).first(), False
        except Exception as exc:
            session.rollback()
            LOGGER.error("创建商城订单记录失败 downstream=%s: %s", values.get("downstream_order_no"), exc)
            return None, False


def sql_get_shop_order(order_id: int) -> Optional[ShopOrder]:
    with Session() as session:
        try:
            return _reload(session, order_id)
        except Exception as exc:
            LOGGER.error("查询商城订单失败 id=%s: %s", order_id, exc)
            return None


def sql_get_shop_order_by_downstream(downstream_order_no: str) -> Optional[ShopOrder]:
    with Session() as session:
        try:
            return session.query(ShopOrder).filter(
                ShopOrder.downstream_order_no == downstream_order_no
            ).first()
        except Exception as exc:
            LOGGER.error("按商城订单号查询失败 downstream=%s: %s", downstream_order_no, exc)
            return None


def sql_update_shop_order(order_id: int, **values) -> Optional[ShopOrder]:
    """Apply one durable state transition and return the refreshed detached row."""
    with Session() as session:
        try:
            row = _reload(session, order_id)
            if row is None:
                return None
            for key, value in values.items():
                if hasattr(ShopOrder, key):
                    setattr(row, key, value)
            row.updated_at = datetime.now()
            session.commit()
            return row
        except Exception as exc:
            session.rollback()
            LOGGER.error("更新商城订单失败 id=%s: %s", order_id, exc)
            return None


def sql_append_shop_order_error(order_id: int, note: str) -> Optional[ShopOrder]:
    row = sql_get_shop_order(order_id)
    if row is None:
        return None
    previous = (row.error_message or "").strip()
    merged = f"{previous}; {note}" if previous else note
    return sql_update_shop_order(order_id, error_message=merged[:255])


def sql_list_shop_orders(query: str = "", limit: int = 20) -> list[ShopOrder]:
    with Session() as session:
        try:
            limit = max(1, min(int(limit), 100))
            query = str(query or "").strip()
            stmt = session.query(ShopOrder)
            if query:
                terms = [
                    ShopOrder.order_no == query,
                    ShopOrder.downstream_order_no == query,
                ]
                if query.isdigit():
                    terms.append(ShopOrder.tg == int(query))
                stmt = stmt.filter(or_(*terms))
            return stmt.order_by(ShopOrder.id.desc()).limit(limit).all()
        except Exception as exc:
            LOGGER.error("查询商城订单列表失败 query=%s: %s", query, exc)
            return []


# Compatibility names for any integration code that used the concise helpers.
def get_shop_order_by_downstream(order_no: str):
    return sql_get_shop_order_by_downstream(order_no)


def get_shop_order(order_id: int):
    return sql_get_shop_order(order_id)


def save_shop_order(order: ShopOrder) -> bool:
    values = {
        key: value for key, value in vars(order).items()
        if key != "_sa_instance_state" and hasattr(ShopOrder, key)
    }
    values.pop("id", None)
    return sql_update_shop_order(order.id, **values) is not None


__all__ = [
    "ShopOrder",
    "sql_create_shop_order",
    "sql_get_shop_order",
    "sql_get_shop_order_by_downstream",
    "sql_update_shop_order",
    "sql_append_shop_order_error",
    "sql_list_shop_orders",
    "get_shop_order_by_downstream",
    "get_shop_order",
    "save_shop_order",
]
