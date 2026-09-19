"""
启动面板start命令 返回面ban

+ myinfo 个人数据
+ count  服务器媒体数
"""
import asyncio
from pyrogram import filters

from bot.func_helper.emby import Embyservice
from bot.func_helper.utils import judge_admins, members_info
from bot.func_helper.filters import user_in_group_filter, user_in_group_on_filter
from bot.func_helper.msg_utils import deleteMessage, sendMessage, sendPhoto, callAnswer, editMessage
from bot.func_helper.fix_bottons import group_f, judge_start_ikb, judge_group_ikb, cr_kk_ikb
from bot.modules.extra import user_cha_ip
from bot.sql_helper.sql_emby import sql_add_emby, sql_get_emby
from bot import bot, prefixes, group, bot_photo, ranks


# 反命令提示
@bot.on_message((filters.command('start', prefixes) | filters.command('count', prefixes)) & filters.chat(group))
async def ui_g_command(_, msg):
    await asyncio.gather(deleteMessage(msg),
                         sendMessage(msg,
                                     f"[{msg.from_user.first_name}](tg://user?id={msg.from_user.id}) 这是一条私聊命令",
                                     buttons=group_f, timer=60))


# 查看自己的信息
@bot.on_message(filters.command('myinfo', prefixes) & user_in_group_on_filter)
async def my_info(_, msg):
    await msg.delete()
    if msg.sender_chat:
        return
    text, keyboard = await cr_kk_ikb(uid=msg.from_user.id, first=msg.from_user.first_name)
    await sendMessage(msg, text, timer=60)


@bot.on_message(filters.command('count', prefixes) & user_in_group_on_filter & filters.private)
async def count_info(_, msg):
    await deleteMessage(msg)
    text = await Embyservice.get_medias_count()
    await sendMessage(msg, text, timer=60)


# 私聊开启面板
@bot.on_message(filters.command('start', prefixes) & filters.private)
async def p_start(_, msg):
    if not await user_in_group_filter(_, msg):
        return await asyncio.gather(deleteMessage(msg),
                                    sendMessage(msg,
                                                '请先点击下面加入我们的群组和频道，然后再 /start。\n\n'
                                                '说明：如果您已在群组中且收到此消息，请联系管理员解除您的权限限制，因为被限制用户无法使用此bot。',
                                                buttons=judge_group_ikb))
    exist_emby_data = sql_get_emby(msg.from_user.id)
    if not exist_emby_data:
        sql_add_emby(msg.from_user.id)
    data = await members_info(tg=msg.from_user.id)
    if not data:
        return await sendMessage(msg, "出现错误，请稍后再试")
    is_admin = judge_admins(msg.from_user.id)
    name, lv, ex, embyid = data
    text = f"__用户面板：{msg.from_user.first_name}__\n\n" \
           f"**· TG ID** | `{msg.from_user.id}`\n" \
           f"**· 当前状态** | {lv}\n" \
           f"**· 到期时间** | {ex}\n"
    await asyncio.gather(deleteMessage(msg),
                         sendPhoto(msg, bot_photo, caption=text,
                                   buttons=judge_start_ikb(is_admin, bool(embyid))))

# 返回面板
@bot.on_callback_query(filters.regex('back_start'))
async def b_start(_, call):
    if await user_in_group_filter(_, call):
        is_admin = judge_admins(call.from_user.id)
        await asyncio.gather(callAnswer(call, "返回面板"),
                             editMessage(call,
                                         text="__请选择功能__",
                                         buttons=judge_start_ikb(is_admin, account=True)))
    elif not await user_in_group_filter(_, call):
        await asyncio.gather(callAnswer(call, "返回面板"),
                             editMessage(call, text='请先点击下面加入我们的群组和频道，然后再 /start。\n\n'
                                                    '说明：如果您已在群组中且收到此消息，请联系管理员解除您的权限限制，因为被限制用户无法使用此bot。',
                                         buttons=judge_group_ikb))
