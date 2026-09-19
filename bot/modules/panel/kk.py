"""
kk - 用户账户管理
赠与账户，禁用，删除
"""
import pyrogram
from pyrogram import filters
from pyrogram.errors import BadRequest
from bot import bot, prefixes, owner, admins, LOGGER
from bot.func_helper.emby import emby, emby_del_all, emby_policy_all
from bot.func_helper.filters import admins_on_filter
from bot.func_helper.fix_bottons import cr_kk_ikb
from bot.func_helper.msg_utils import deleteMessage, sendMessage, editMessage
from bot.func_helper.utils import judge_admins
from bot.sql_helper.sql_emby import sql_add_emby, sql_get_emby, sql_update_emby, Emby


# 管理用户
@bot.on_message(filters.command('kk', prefixes) & admins_on_filter)
async def user_info(_, msg):
    await deleteMessage(msg)
    if msg.reply_to_message is None:
        try:
            uid = int(msg.command[1])
            if not msg.sender_chat:
                if msg.from_user.id != owner and uid == owner:
                    return await sendMessage(msg,
                                             f"[{msg.from_user.first_name}](tg://user?id={msg.from_user.id}) 无权查询该账户",
                                             timer=60)
            else:
                pass
            first = await bot.get_chat(uid)
        except (IndexError, KeyError, ValueError):
            return await sendMessage(msg, '**请先给我一个tg_id！**\n\n用法：/kk [tg_id]\n或者对某人回复kk', timer=60)
        except BadRequest:
            return await sendMessage(msg, f'{msg.command[1]} - 此id未登记bot，或者id错误', timer=60)
        except AttributeError:
            pass
        else:
            sql_add_emby(uid)
            text, keyboard = await cr_kk_ikb(uid, first.first_name)
            await sendMessage(msg, text=text, buttons=keyboard)  # protect_content=True 移除禁止复制

    else:
        uid = msg.reply_to_message.from_user.id
        try:
            if msg.from_user.id != owner and uid == owner:
                return await msg.reply(
                    f"[{msg.from_user.first_name}](tg://user?id={msg.from_user.id}) 无权查询该账户")
        except AttributeError:
            pass

        sql_add_emby(uid)
        text, keyboard = await cr_kk_ikb(uid, msg.reply_to_message.from_user.first_name)
        await sendMessage(msg, text=text, buttons=keyboard)


# 封禁或者解除
@bot.on_callback_query(filters.regex('user_ban'))
async def kk_user_ban(_, call):
    if not judge_admins(call.from_user.id):
        return await call.answer("管理员权限不足", show_alert=True)

    await call.answer("处理中")
    b = int(call.data.split("-")[1])
    if b in admins and b != call.from_user.id:
        return await editMessage(call,
                                 f"机器人不可以对bot管理员执行此操作，请[自己](tg://user?id={call.from_user.id})解决",
                                 timer=60)

    first = await bot.get_chat(b)
    e = sql_get_emby(tg=b)
    if e.embyid is None:
        await editMessage(call, f'该用户没有注册账户。', timer=60)
    else:
        text = f'管理员 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) 对 [{first.first_name}](tg://user?id={b}) - {e.name} 的'
        if e.lv != "c":
            if await emby_policy_all(tg=b, embyid=e.embyid, disable=True) is True:
                if sql_update_emby(Emby.tg == b, lv='c') is True:
                    text += f'封禁完成，此状态可在下次续期时刷新'
                    LOGGER.info(text)
                else:
                    text += '封禁失败，已执行，但数据库写入错误'
                    LOGGER.error(text)
            else:
                text += f'封禁失败，请检查emby服务器。响应错误'
                LOGGER.error(text)
        elif e.lv == "c":
            if await emby_policy_all(tg=b, embyid=e.embyid):
                if sql_update_emby(Emby.tg == b, lv='b'):
                    text += '解禁完成'
                    LOGGER.info(text)
                else:
                    text += '解禁失败，服务器已执行，数据库写入错误'
                    LOGGER.error(text)
            else:
                text += '解封失败，请检查emby服务器。响应错误'
                LOGGER.error(text)
        await editMessage(call, text)
        await bot.send_message(b, text)




# 删除账户
@bot.on_callback_query(filters.regex('closeemby'))
async def close_emby(_, call):
    if not judge_admins(call.from_user.id):
        return await call.answer("管理员权限不足", show_alert=True)

    await call.answer("处理中")
    b = int(call.data.split("-")[1])
    if b in admins and b != call.from_user.id:
        return await editMessage(call,
                                 f"机器人不可以对bot管理员执行此操作，请[自己](tg://user?id={call.from_user.id})解决",
                                 timer=60)

    first = await bot.get_chat(b)
    e = sql_get_emby(tg=b)
    if e.embyid is None:
        return await editMessage(call, f'该用户还没有注册账户。', timer=60)

    if await emby_del_all(tg=b, embyid=e.embyid):
        sql_update_emby(Emby.embyid == e.embyid, embyid=None, name=None, pwd=None, lv='d', cr=None, ex=None)
        await editMessage(call,
                          f'管理员 [{call.from_user.first_name}](tg://user?id={call.from_user.id})\\n等级：{e.lv} - [{first.first_name}](tg://user?id={b}) '
                          f'账户 {e.name} 已完成删除。')
        await bot.send_message(b,
                               f"管理员 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) 已删除该用户的账户 {e.name}")
        LOGGER.info(f"【admin】：{call.from_user.id} 完成删除 {b} 的账户 {e.name}")
    else:
        await editMessage(call, f'等级：{e.lv} - {first.first_name}的账户 {e.name} 删除失败。')
        LOGGER.info(f"【admin】：{call.from_user.id} 对 {b} 的账户 {e.name} 删除失败 ")


@bot.on_callback_query(filters.regex('fuckoff'))
async def fuck_off_m(_, call):
    if not judge_admins(call.from_user.id):
        return await call.answer("管理员权限不足", show_alert=True)

    await call.answer("处理中")
    user_id = int(call.data.split("-")[1])
    if user_id in admins and user_id != call.from_user.id:
        return await editMessage(call,
                                 f"机器人不可以对bot管理员执行此操作，请[自己](tg://user?id={call.from_user.id})解决",
                                 timer=60)
    try:
        user = await bot.get_chat(user_id)
        await call.message.chat.ban_member(user_id)  # 默认退群了就删号    fix：call 没有对象chat
        await editMessage(call,
                          f'管理员 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) 已移除 [{user.first_name}](tg://user?id={user_id})[{user_id}]')
        LOGGER.info(
            f"【admin】：{call.from_user.id} 已从群组 {call.message.chat.id} 封禁 {user.first_name} - {user.id}")
    except pyrogram.errors.ChatAdminRequired:
        await editMessage(call,
                          f"请赋予机器人踢出成员的权限 [{call.from_user.first_name}](tg://user?id={call.from_user.id})")
    except pyrogram.errors.UserAdminInvalid:
        await editMessage(call,
                          f"机器人不可以对群组管理员执行此操作，请[自己](tg://user?id={call.from_user.id})解决")
