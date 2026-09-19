"""Synchronous fulfillment service for the dujiao-next upstream contract.

The order row is the source of truth.  ``submit_order`` creates it before any
Emby side effect, serializes one TG at a time with the existing user lock, and
records a durable operation stage after each boundary.  HTTP transport must
only expose the neutral fields returned by :func:`order_result`.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Optional

from bot import LOGGER, bot, owner
from bot.func_helper.concurrency import get_user_lock
from bot.func_helper.emby import (
    emby_create_all,
    emby_policy_all,
    primary_server_name,
    render_server_lines,
    target_servers,
    get_emby,
)
from bot.func_helper.msg_utils import sendMessage
from bot.func_helper.utils import pwd_create
from bot.sql_helper.sql_emby import (
    Emby,
    sql_add_server_account,
    sql_get_emby,
    sql_update_emby,
)
from bot.sql_helper.sql_shop import (
    ShopOrder,
    sql_append_shop_order_error,
    sql_create_shop_order,
    sql_get_shop_order,
    sql_get_shop_order_by_downstream,
    sql_list_shop_orders,
    sql_update_shop_order,
)

SKU_DAYS = {"1": 30, "2": 90, "3": 180, "DAYS-30": 30, "DAYS-90": 90, "DAYS-180": 180}
SKU_WL = {"4", "WL-PERM"}


def _now() -> datetime:
    return datetime.now()


def _new_order_no() -> str:
    # The database unique key remains the final collision guard.
    return "SK" + _now().strftime("%Y%m%d%H%M%S%f")[:18] + secrets.token_hex(2)


def _transient(status: str, message: str, **values) -> ShopOrder:
    row = ShopOrder(
        order_no=values.get("order_no", ""),
        downstream_order_no=values.get("downstream_order_no", ""),
        trace_id=values.get("trace_id"),
        sku_code=values.get("sku_code", "INVALID"),
        quantity=int(values.get("quantity", 1) or 1),
        days=int(values.get("days", 0) or 0),
        tg=int(values.get("tg", 0) or 0),
        status=status,
        error_message=message[:255],
        operation_stage="not_persisted",
        created_at=_now(),
        updated_at=_now(),
    )
    return row


def order_result(row: ShopOrder) -> dict[str, Any]:
    """Neutral payload suitable for all HTTP responses (never credentials)."""
    return {
        "ok": True,
        "order_id": row.id,
        "order_no": row.order_no,
        "status": "delivered",
        "amount": "0.00",
        "currency": "CNY",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class OrderPersistenceError(RuntimeError):
    """A durable transition failed; never continue to a remote side effect."""


def _must_save(order_id: int, **values) -> ShopOrder:
    row = sql_update_shop_order(order_id, **values)
    if row is None:
        raise OrderPersistenceError(f"订单状态落库失败 id={order_id}")
    return row


def _json_servers(row: ShopOrder) -> dict[str, Any]:
    try:
        value = json.loads(row.server_results or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _save(row_id: int, **values) -> Optional[ShopOrder]:
    return sql_update_shop_order(row_id, **values)


def _existing_name(name: str) -> bool:
    existing = sql_get_emby(name)
    return bool(existing and existing.name == name)


async def _random_account_name() -> Optional[str]:
    letters = string.ascii_lowercase
    digits = string.digits
    for _ in range(10):
        name = "".join(secrets.choice(letters) for _ in range(3)) + "".join(
            secrets.choice(digits) for _ in range(3)
        )
        if not _existing_name(name):
            return name
    return None


async def _recover_created_accounts(row: ShopOrder) -> Optional[dict[str, Any]]:
    """Find a remote account left behind by a crash between create and commit."""
    if not row.emby_name:
        return None
    recovered: dict[str, Any] = {}
    for server in target_servers("b"):
        try:
            ok, data = await asyncio.wait_for(
                get_emby(server.name).get_emby_user_by_name(row.emby_name), 4.0
            )
            if ok and isinstance(data, dict) and data.get("Id"):
                recovered[server.name] = {"embyid": data["Id"], "status": "active"}
        except Exception as exc:
            LOGGER.warning("恢复商城订单远程账户失败 server=%s: %s", server.name, exc)
    primary = primary_server_name()
    if primary not in recovered:
        return None
    return recovered


async def _notify(row: ShopOrder) -> None:
    """Best-effort Telegram delivery; notification state is persisted."""
    if row.status != "ok" or not row.tg:
        return
    if row.sku_code in SKU_WL:
        try:
            await bot.send_message(row.tg, "商城白名单已开通，您的 Emby 账号已升级为永久白名单。")
            _save(row.id, notify_state="sent")
        except Exception as exc:
            LOGGER.warning("商城白名单通知失败 id=%s: %s", row.id, exc)
            _save(row.id, notify_state="failed", error_message=f"通知失败: {exc}"[:255])
        try:
            await bot.send_message(owner, f"商城白名单备案：TG `{row.tg}`，订单 `{row.order_no}`")
        except Exception as exc:
            LOGGER.warning("商城 owner 备案失败 id=%s: %s", row.id, exc)
        return
    try:
        lines = render_server_lines(tg=row.tg, lv=row.lv_after, embyid=row.embyid)
        if row.created_account:
            text = (f"商城开通成功\n账号：`{row.emby_name}`\n密码：`{row.account_password or '请联系管理员'}`\n"
                    f"到期时间：{row.ex_after}\n线路：\n{lines}")
        else:
            text = f"商城续期成功\n账号：`{row.emby_name}`\n到期时间：{row.ex_after}\n线路：\n{lines}"
        await bot.send_message(row.tg, text)
        if _save(row.id, notify_state="sent") is None:
            LOGGER.error("商城订单通知成功但状态未落库 id=%s", row.id)
    except Exception as exc:
        LOGGER.warning("商城订单通知失败 id=%s: %s", row.id, exc)
        _save(row.id, notify_state="failed", error_message=f"通知失败: {exc}"[:255])


async def _alert(row: ShopOrder, reason: str) -> None:
    try:
        await bot.send_message(owner, f"商城订单异常：订单 `{row.order_no}`，状态 `{row.status}`，原因：{reason[:180]}")
    except Exception as exc:
        LOGGER.warning("商城 owner 告警失败 id=%s: %s", getattr(row, "id", None), exc)


async def _fulfill(row: ShopOrder) -> ShopOrder:
    """Execute or recover one persisted order while holding its TG lock."""
    if row.status == "ok":
        return row
    async with get_user_lock(int(row.tg)):
        row = sql_get_shop_order(row.id) or row
        if row.status == "ok":
            return row
        now = _now()
        emby_row = sql_get_emby(tg=row.tg) if row.tg else None
        if not emby_row:
            row = _must_save(row.id, status="no_such_tg", operation_stage="validated", error_message="TG 不存在")
            await _alert(row, row.error_message or "TG 不存在")
            return row
        try:
            if row.sku_code in SKU_WL:
                if not emby_row.embyid:
                    row = _must_save(row.id, status="no_account_for_whitelist", operation_stage="validated", error_message="白名单需要已有账号")
                    await _alert(row, row.error_message or "无账号")
                    return row
                row = _must_save(row.id, operation_stage="account_update_pending", embyid=emby_row.embyid,
                                 emby_name=emby_row.name, ex_before=emby_row.ex, ex_after=emby_row.ex,
                                 lv_before=emby_row.lv, lv_after="a", days=0)
                if not sql_update_emby(Emby.tg == row.tg, lv="a"):
                    raise RuntimeError("白名单数据库更新失败")
                row = _must_save(row.id, operation_stage="account_updated", status="ok")
                asyncio.create_task(_notify(row), name=f"shop-notify-{row.id}")
                return row

            days = row.days
            if days <= 0:
                row = _must_save(row.id, status="emby_error", operation_stage="validated", error_message="无效 SKU")
                await _alert(row, row.error_message or "无效 SKU")
                return row

            if not emby_row.embyid:
                if not row.emby_name:
                    name = await _random_account_name()
                    if not name:
                        raise RuntimeError("随机账号名碰撞超过 10 次")
                    password = await pwd_create(8)
                    row = _must_save(row.id, emby_name=name, account_password=password,
                                     created_account=1, lv_before=emby_row.lv,
                                     operation_stage="creating_account")
                if row.operation_stage == "creating_account":
                    accounts = await _recover_created_accounts(row)
                    if accounts is None:
                        created = await asyncio.wait_for(
                            emby_create_all(name=row.emby_name, days=days, lv="b", password=row.account_password), 18.0
                        )
                        if not created.ok:
                            raise RuntimeError("主服建号失败")
                        accounts = {server: {"embyid": eid, "status": status}
                                    for server, eid, status in created.accounts}
                    primary = accounts.get(primary_server_name(), {})
                    if not primary.get("embyid"):
                        raise RuntimeError("主服账户未返回 ID")
                    row = _must_save(row.id, embyid=primary["embyid"], operation_stage="remote_accounts",
                                     server_results=json.dumps(accounts))
                if row.operation_stage == "remote_accounts":
                    accounts = _json_servers(row)
                    for server, data in accounts.items():
                        if data.get("embyid"):
                            if not sql_add_server_account(row.tg, server, data["embyid"], row.emby_name,
                                                          data.get("status", "active")):
                                raise RuntimeError(f"服务器账户落库失败: {server}")
                    ex_after = row.ex_after or (_now() + timedelta(days=days))
                    if not sql_update_emby(Emby.tg == row.tg, embyid=row.embyid, name=row.emby_name,
                                           pwd=row.account_password, lv="b", cr=now, ex=ex_after):
                        raise RuntimeError("主账号落库失败")
                    row = _must_save(row.id, ex_after=ex_after, lv_after="b", status="ok",
                                     operation_stage="account_updated")
            else:
                if (row.created_account and row.embyid == emby_row.embyid
                        and row.operation_stage in ("remote_accounts", "account_updated")):
                    row = _must_save(row.id, ex_after=emby_row.ex, lv_after=emby_row.lv,
                                     status="ok", operation_stage="account_updated")
                    asyncio.create_task(_notify(row), name=f"shop-notify-{row.id}")
                    return row
                if (row.operation_stage == "account_update_pending" and row.ex_after is not None
                        and emby_row.ex == row.ex_after):
                    row = _must_save(row.id, status="ok", operation_stage="account_updated")
                    asyncio.create_task(_notify(row), name=f"shop-notify-{row.id}")
                    return row
                base = emby_row.ex if emby_row.ex and emby_row.ex > now else now
                ex_after = base + timedelta(days=days)
                lv_after = "a" if emby_row.lv == "a" else "b"
                row = _must_save(row.id, embyid=emby_row.embyid, emby_name=emby_row.name,
                                 ex_before=emby_row.ex, ex_after=ex_after, lv_before=emby_row.lv,
                                 lv_after=lv_after, operation_stage="account_update_pending")
                if ex_after > now and emby_row.lv != "a":
                    if not await asyncio.wait_for(emby_policy_all(tg=row.tg, embyid=emby_row.embyid,
                                                                  disable=False), 8.0):
                        raise RuntimeError("恢复 Emby 播放策略失败")
                if not sql_update_emby(Emby.tg == row.tg, ex=ex_after, lv=lv_after):
                    raise RuntimeError("续期数据库更新失败")
                row = _must_save(row.id, status="ok", operation_stage="account_updated")
            asyncio.create_task(_notify(row), name=f"shop-notify-{row.id}")
            return row
        except Exception as exc:
            message = str(exc)[:255]
            saved = _save(row.id, status="emby_error", error_message=message, operation_stage=row.operation_stage)
            row = saved or row
            await _alert(row, message)
            return row

async def submit_order(payload: dict) -> ShopOrder:
    """Validate, persist, and synchronously fulfill one upstream order."""
    payload = payload if isinstance(payload, dict) else {}
    downstream = str(payload.get("downstream_order_no") or "").strip()
    trace_id = str(payload.get("trace_id") or "")[:64] or None
    raw_sku = payload.get("sku_id", payload.get("sku_code"))
    sku = str(raw_sku or "")
    quantity = payload.get("quantity", 1)
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 0
    form = payload.get("manual_form_data") or {}
    raw_tg = str(form.get("tg_id") or "").strip()
    tg = int(raw_tg) if raw_tg.isdigit() else 0
    days_each = SKU_DAYS.get(sku, 0)
    days = days_each * quantity if days_each and 1 <= quantity <= 100 else 0
    if not downstream:
        return _transient("db_error", "缺少商城幂等订单号", downstream_order_no=downstream, tg=tg, sku_code=sku, quantity=quantity)
    existing = sql_get_shop_order_by_downstream(downstream)
    if existing is not None:
        return await _fulfill(existing) if existing.status not in ("ok", "no_such_tg", "no_account_for_whitelist") else existing
    values = dict(order_no=_new_order_no(), downstream_order_no=downstream, trace_id=trace_id, sku_code=("WL-PERM" if sku in SKU_WL else f"DAYS-{days_each}" if days_each else "INVALID"), quantity=max(quantity, 0), days=days, tg=tg, status="processing", operation_stage="prepared", created_at=_now(), updated_at=_now())
    row, inserted = sql_create_shop_order(**values)
    if row is None:
        existing = sql_get_shop_order_by_downstream(downstream)
        return existing or _transient("db_error", "订单记录无法持久化", **values)
    if not inserted:
        return await _fulfill(row) if row.status not in ("ok", "no_such_tg", "no_account_for_whitelist") else row
    if not tg or (not days and sku not in SKU_WL):
        row = _must_save(row.id, status="emby_error", operation_stage="validated", error_message="无效 TG 或 SKU")
        await _alert(row, row.error_message or "无效请求")
        return row
    return await _fulfill(row)


def get_order(order_id: int) -> Optional[ShopOrder]:
    return sql_get_shop_order(order_id)


def cancel_order(order_id: int) -> None:
    row = sql_get_shop_order(order_id)
    if row:
        sql_append_shop_order_error(order_id, "商城请求取消，服务未撤销")


def list_orders(query: str = "", limit: int = 20) -> list[ShopOrder]:
    return sql_list_shop_orders(query=query, limit=limit)


async def replay_order(order_ref: str) -> ShopOrder:
    """Replay only an internally failed order; successful orders are immutable."""
    ref = str(order_ref or "").strip()
    row = sql_get_shop_order(int(ref)) if ref.isdigit() else None
    if row is None:
        row = sql_get_shop_order_by_downstream(ref)
    if row is None:
        return _transient("db_error", "订单不存在", downstream_order_no=ref)
    if row.status == "ok":
        return row
    source_id = row.id
    values = {
        "order_no": _new_order_no(),
        "downstream_order_no": f"replay:{row.downstream_order_no}:{source_id}:{secrets.token_hex(4)}",
        "trace_id": row.trace_id,
        "sku_code": row.sku_code,
        "quantity": row.quantity,
        "days": row.days,
        "tg": row.tg,
        "status": "processing",
        "operation_stage": row.operation_stage,
        "embyid": row.embyid,
        "server_results": row.server_results,
        "emby_name": row.emby_name,
        "account_password": row.account_password,
        "created_account": row.created_account,
        "replayed_from": source_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    replay, inserted = sql_create_shop_order(**values)
    if replay is None:
        return _transient("db_error", "重放订单无法持久化", **values)
    if not inserted:
        return replay
    return await _fulfill(replay)


__all__ = ["submit_order", "get_order", "cancel_order", "list_orders", "replay_order", "order_result"]
