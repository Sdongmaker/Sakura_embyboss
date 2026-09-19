"""Administrator-only shop reconciliation commands."""
from __future__ import annotations

from pyrogram import filters
from pyrogram.types import Message

from bot import bot, prefixes
from bot.func_helper.filters import admins_on_filter
from bot.func_helper.msg_utils import sendMessage
from bot.func_helper.shop import list_orders, get_order, replay_order


def _safe_row(row) -> str:
    return (
        f"#{row.id} `{row.order_no}`\n"
        f"商城单号：`{row.downstream_order_no}`\n"
        f"TG：`{row.tg}` SKU：`{row.sku_code}` 数量：{row.quantity}\n"
        f"状态：`{row.status}` 阶段：`{row.operation_stage}` 通知：`{row.notify_state}`\n"
        f"账号：`{row.emby_name or '-'} ` 到期：`{row.ex_after or '-'}`\n"
        f"错误：{row.error_message or '-'}"
    )


@bot.on_message(filters.command("shop_orders", prefixes) & admins_on_filter)
async def shop_orders_command(_, message: Message):
    args = (message.text or "").split(maxsplit=1)
    query = args[1].strip() if len(args) > 1 else ""
    rows = list_orders(query=query, limit=20)
    if not rows:
        return await sendMessage(message, "没有找到商城订单。")
    text = "\n\n".join(_safe_row(row) for row in rows)
    return await sendMessage(message, text)


@bot.on_message(filters.command("shop_order", prefixes) & admins_on_filter)
async def shop_order_command(_, message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        return await sendMessage(message, "用法：/shop_order 订单ID")
    ref = args[1].strip()
    row = get_order(int(ref)) if ref.isdigit() else None
    if row is None:
        return await sendMessage(message, "未找到该订单。")
    return await sendMessage(message, _safe_row(row))


@bot.on_message(filters.command("shop_replay", prefixes) & admins_on_filter)
async def shop_replay_command(_, message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        return await sendMessage(message, "用法：/shop_replay 订单ID或商城订单号")
    row = await replay_order(args[1].strip())
    return await sendMessage(message, _safe_row(row))
