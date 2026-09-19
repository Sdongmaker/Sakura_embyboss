"""Dujiao-Next upstream protocol endpoints.

The bot is the upstream supplier.  All endpoint handlers are deliberately
thin: authentication is performed against the exact raw request bytes and
business state is delegated to ``bot.func_helper.shop``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from bot import LOGGER, config

router = APIRouter(prefix="/api/v1/upstream", tags=["dujiao-next upstream"])

_FORM_SCHEMA = {
    "fields": [{
        "key": "tg_id",
        "type": "text",
        "label": {"zh-CN": "Telegram ID", "zh-TW": "Telegram ID", "en-US": "Telegram ID"},
        "placeholder": {
            "zh-CN": "请从 Telegram 机器人复制你的数字 ID",
            "zh-TW": "請從 Telegram 機器人複製你的數字 ID",
            "en-US": "Copy your numeric ID from the Telegram bot",
        },
        "required": True,
        "regex": "/^[0-9]{5,15}$/",
        "max_len": 15,
    }]
}


def _shop():
    return getattr(config, "shop", None)


def _verify(request: Request, body: bytes) -> None:
    shop = _shop()
    if shop is None or not bool(getattr(shop, "enabled", False)):
        raise HTTPException(status_code=404, detail="upstream disabled")
    api_key = request.headers.get("Dujiao-Next-Api-Key", "")
    timestamp_text = request.headers.get("Dujiao-Next-Timestamp", "")
    signature = request.headers.get("Dujiao-Next-Signature", "")
    try:
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="invalid signature") from None
    if abs(int(time.time()) - timestamp) > 60:
        raise HTTPException(status_code=401, detail="invalid signature")
    if not api_key or not hmac.compare_digest(api_key, str(getattr(shop, "api_key", ""))):
        raise HTTPException(status_code=401, detail="invalid signature")
    path = request.url.path
    body_md5 = hashlib.md5(body).hexdigest()
    sign_string = f"{request.method}\n{path}\n{timestamp}\n{body_md5}"
    expected = hmac.new(
        str(getattr(shop, "api_secret", "")).encode(), sign_string.encode(), hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid signature")


async def _authenticated(request: Request) -> bytes:
    body = await request.body()
    _verify(request, body)
    return body


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone(timedelta(hours=8)))
        return value.isoformat()
    return str(value)


def _order_response(order: Any) -> dict[str, Any]:
    data = _as_dict(order)
    return {
        "ok": True,
        "order_id": data.get("id", data.get("order_id")),
        "order_no": data.get("order_no", ""),
        "status": "delivered",
        "amount": "0.00",
        "currency": "CNY",
    }


def _order_detail(order: Any) -> dict[str, Any]:
    data = _as_dict(order)
    delivered_at = data.get("updated_at") or data.get("created_at")
    return {
        "order_id": data.get("id", data.get("order_id")),
        "order_no": data.get("order_no", ""),
        "status": "delivered",
        "amount": "0.00",
        "currency": "CNY",
        "fulfillment": {
            "type": "manual",
            "status": "delivered",
            "payload": "账号信息已通过 Telegram 发送",
            "delivery_data": {"note": "账号信息已通过 Telegram 发送"},
            "delivered_at": _iso(delivered_at),
        },
    }


def _products() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "title": {"zh-CN": "会员天数卡", "en-US": "Membership Days Card"},
            "description": {"zh-CN": "延长账号有效期", "en-US": "Extend your account"},
            "content": {"zh-CN": "购买后由 Telegram 机器人自动开通并发送账号信息。", "en-US": "Delivered by Telegram bot."},
            "images": [], "tags": ["会员"], "price_amount": "0.00", "currency": "CNY",
            "fulfillment_type": "manual", "manual_form_schema": _FORM_SCHEMA,
            "is_active": True, "category_id": 1,
            "skus": [
                {"id": 1, "sku_code": "DAYS-30", "spec_values": {"zh-CN": "30 天"}, "price_amount": "0.00", "stock_status": "unlimited", "stock_quantity": -1, "is_active": True},
                {"id": 2, "sku_code": "DAYS-90", "spec_values": {"zh-CN": "90 天"}, "price_amount": "0.00", "stock_status": "unlimited", "stock_quantity": -1, "is_active": True},
                {"id": 3, "sku_code": "DAYS-180", "spec_values": {"zh-CN": "180 天"}, "price_amount": "0.00", "stock_status": "unlimited", "stock_quantity": -1, "is_active": True},
            ],
            "updated_at": "2026-09-19T12:00:00+08:00",
        },
        {
            "id": 2,
            "title": {"zh-CN": "永久白名单卡", "en-US": "Permanent Whitelist"},
            "description": {"zh-CN": "一次性开通永久白名单", "en-US": "Enable permanent whitelist"},
            "content": {"zh-CN": "购买后由 Telegram 机器人自动开通并发送账号信息。", "en-US": "Delivered by Telegram bot."},
            "images": [], "tags": ["白名单"], "price_amount": "0.00", "currency": "CNY",
            "fulfillment_type": "manual", "manual_form_schema": _FORM_SCHEMA,
            "is_active": True, "category_id": 1,
            "skus": [{"id": 4, "sku_code": "WL-PERM", "spec_values": {"zh-CN": "永久"}, "price_amount": "0.00", "stock_status": "unlimited", "stock_quantity": -1, "is_active": True}],
            "updated_at": "2026-09-19T12:00:00+08:00",
        },
    ]


@router.post("/ping")
async def ping(request: Request):
    await _authenticated(request)
    shop = _shop()
    return {"ok": True, "site_name": getattr(shop, "site_name", "Sakura Emby"), "protocol_version": "1.0", "user_id": 1, "balance": "0.00", "currency": "CNY", "member_level": {}}


@router.get("/categories")
async def categories(request: Request):
    await _authenticated(request)
    return {"ok": True, "categories": [{"id": 1, "name": {"zh-CN": "会员服务", "en-US": "Membership"}, "slug": "membership", "sort_order": 1}]}


@router.get("/products")
async def products(request: Request):
    await _authenticated(request)
    return {"ok": True, "total": 2, "items": _products(), "includes_inactive": True}


@router.get("/products/{product_id}")
async def product(product_id: int, request: Request):
    await _authenticated(request)
    item = next((item for item in _products() if item["id"] == product_id), None)
    if item is None:
        return JSONResponse(status_code=404, content={"error_code": "product_not_found", "error_message": "product not found"})
    return {"ok": True, "product": item}


@router.post("/orders")
async def create_order(request: Request):
    body = await _authenticated(request)
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json") from None
    from bot.func_helper.shop import submit_order
    order = await submit_order(payload)
    return _order_response(order)


@router.get("/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    await _authenticated(request)
    from bot.func_helper.shop import get_order
    order = get_order(order_id)
    if order is None:
        return JSONResponse(status_code=404, content={"error_code": "order_not_found", "error_message": "order not found"})
    return _order_detail(order)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int, request: Request):
    await _authenticated(request)
    from bot.func_helper.shop import cancel_order
    cancel_order(order_id)
    return {"ok": True}
