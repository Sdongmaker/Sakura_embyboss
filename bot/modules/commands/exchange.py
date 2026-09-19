"""Renewal and whitelist code redemption."""
from datetime import datetime, timedelta

from bot import bot, _open, LOGGER
from bot.func_helper.concurrency import get_user_lock
from bot.func_helper.msg_utils import sendMessage
from bot.sql_helper.sql_code import Code
from bot.sql_helper.sql_emby import Emby, sql_get_emby
from bot.sql_helper import Session

def is_renew_code(input_string: str) -> bool:
    return "-Renew_" in input_string


def is_whitelist_code(input_string: str) -> bool:
    return "-Whitelist_" in input_string


def _redeem_whitelist_code_atomic(code_value: str, user_id: int):
    now = datetime.now()
    with Session() as session:
        user = session.query(Emby).filter(Emby.tg == user_id).with_for_update().first()
        if not user:
            return {"status": "no_user"}
        if not user.embyid:
            return {"status": "no_account"}
        code = session.query(Code).filter(Code.code == code_value).with_for_update().first()
        if not code or not is_whitelist_code(code.code):
            return {"status": "invalid_code"}
        if code.used is not None:
            return {"status": "used", "used": code.used}
        if user.lv == "a":
            return {"status": "already_wl"}
        user.lv = "a"
        code.used = user_id
        code.usedtime = now
        session.commit()
        return {"status": "ok", "issuer_tg": code.tg}


def _redeem_renew_code_atomic(code_value: str, user_id: int):
    now = datetime.now()
    with Session() as session:
        user = session.query(Emby).filter(Emby.tg == user_id).with_for_update().first()
        if not user:
            return {"status": "no_user"}
        if not user.embyid:
            return {"status": "no_account"}
        code = session.query(Code).filter(Code.code == code_value).with_for_update().first()
        if not code or not is_renew_code(code.code):
            return {"status": "invalid_code"}
        if code.used is not None:
            return {"status": "used", "used": code.used}

        code.used = user_id
        code.usedtime = now
        current_ex = user.ex or now
        expired = now > current_ex
        ex_new = now + timedelta(days=code.us) if expired else current_ex + timedelta(days=code.us)
        if expired and user.lv == "c":
            user.lv = "b"
        user.ex = ex_new
        session.commit()
        return {
            "status": "ok",
            "issuer_tg": code.tg,
            "days": code.us,
            "ex_new": ex_new,
            "restore_policy": expired,
        }


async def rgs_code(_, msg, register_code):
    """Redeem only renewal and whitelist codes; historical registration codes stay invalid."""
    user_id = msg.from_user.id
    if is_whitelist_code(register_code):
        if not _open.use_whitelist_code:
            return await sendMessage(msg, "管理员未开启白名单码功能。", timer=60)
        async with get_user_lock(user_id):
            result = _redeem_whitelist_code_atomic(register_code, user_id)
        if result["status"] == "no_user":
            return await sendMessage(msg, "出错了，不确定您是否有资格使用，请先 /start")
        if result["status"] == "no_account":
            return await sendMessage(msg, "白名单码需要您先拥有 Emby 账户，请先购买服务后再使用。", timer=60)
        if result["status"] == "invalid_code":
            return await sendMessage(msg, "**无效的白名单码，请确认后重试。**", timer=60)
        if result["status"] == "used":
            return await sendMessage(msg, f'此 `{register_code}` \n白名单码已被 [{result["used"]}](tg://user?id={result["used"]}) 使用。')
        if result["status"] == "already_wl":
            return await sendMessage(msg, "您已是白名单用户，无需重复激活。")
        if result["status"] != "ok":
            return await sendMessage(msg, "未知错误，请稍后重试。")
        try:
            first = await bot.get_chat(result["issuer_tg"])
            issuer_name = f'[{first.first_name}](tg://user?id={result["issuer_tg"]})'
        except Exception:
            issuer_name = str(result["issuer_tg"])
        user_link = f'[{msg.from_user.first_name}](tg://user?id={user_id})'
        masked = register_code[:-7] + "░" * 7
        await sendMessage(msg, f"**白名单已开通**\n\n{user_link} 获得 {issuer_name} 签出的白名单。")
        await sendMessage(msg, f"· 白名单码激活 - {user_link} [{user_id}] 使用了 {masked}", send=True)
        LOGGER.info("【白名单码】：%s[%s] 激活白名单，码：%s", msg.from_user.first_name, user_id, register_code)
        return

    if not is_renew_code(register_code):
        return await sendMessage(msg, "该兑换码无效。注册码和赠送码已停止使用。", timer=60)

    async with get_user_lock(user_id):
        data = sql_get_emby(tg=user_id)
        if not data:
            return await sendMessage(msg, "出错了，不确定您是否有资格使用，请先 /start")
        result = _redeem_renew_code_atomic(register_code, user_id)
    if result["status"] == "invalid_code":
        return await sendMessage(msg, "**续期码无效，请确认后重试。**", timer=60)
    if result["status"] == "used":
        return await sendMessage(msg, f'此 `{register_code}` \n续期码已被 [{result["used"]}](tg://user?id={result["used"]}) 使用。')
    if result["status"] == "no_account":
        return await sendMessage(msg, "续期码仅适用于已有 Emby 账户。", timer=60)
    if result["status"] != "ok":
        return await sendMessage(msg, "未知错误，请稍后重试。")

    try:
        first = await bot.get_chat(result["issuer_tg"])
        issuer_name = f'[{first.first_name}](tg://user?id={result["issuer_tg"]})'
    except Exception:
        issuer_name = str(result["issuer_tg"])
    ex_new = result["ex_new"]
    suffix = "（已解封）" if result["restore_policy"] else ""
    await sendMessage(msg, f"已收到 {issuer_name} 的{result['days']}天续期{suffix}\n到期时间：{ex_new:%Y-%m-%d %H:%M:%S}")
    masked = register_code[:-7] + "░" * 7
    await sendMessage(msg, f"· 续期码使用 - [{msg.from_user.first_name}](tg://user?id={user_id}) [{user_id}] 使用了 {masked}\n· 实时到期 - {ex_new}", send=True)
    LOGGER.info("【续期码】：%s[%s] 使用了 %s，到期时间：%s", msg.from_user.first_name, user_id, register_code, ex_new)
