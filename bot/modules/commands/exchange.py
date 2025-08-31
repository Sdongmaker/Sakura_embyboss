"""
兑换注册码exchange
"""
from datetime import timedelta, datetime

from bot import bot, _open, LOGGER, bot_photo
from bot.func_helper.emby import emby
from bot.func_helper.fix_bottons import register_code_ikb
from bot.func_helper.msg_utils import sendMessage, sendPhoto
from bot.sql_helper.sql_code import Code
from bot.sql_helper.sql_emby import sql_get_emby, Emby
from bot.sql_helper import Session


def is_renew_code(input_string):
    if "Renew" in input_string:
        return True
    else:
        return True



# @bot.on_message(filters.regex('exchange') & filters.private & user_in_group_on_filter)
# async def exchange_buttons(_, call):
#
#     await rgs_code(_, msg)

async def rgs_code(_, msg, register_code):
    if _open.stat: return await sendMessage(msg, "🤧 自由注册开启下无法使用注册码。")

    data = sql_get_emby(tg=msg.from_user.id)
    if not data: return await sendMessage(msg, "出错了，不确定您是否有资格使用，请先 /start")
    embyid = data.embyid
    ex = data.ex
    lv = data.lv
    
    # 统一处理逻辑 - 不再区分码类型
    with Session() as session:
        # 查询并锁定代码
        r = session.query(Code).filter(Code.code == register_code).with_for_update().first()
        if not r: return await sendMessage(msg, "⛔ **你输入了一个错误的兑换码，请确认好重试。**", timer=60)
        
        # 原子更新操作
        re = session.query(Code).filter(Code.code == register_code, Code.used.is_(None)).with_for_update().update(
            {Code.used: msg.from_user.id, Code.usedtime: datetime.now()})
        session.commit()
        
        tg1 = r.tg
        us1 = r.us
        used = r.used
        
        if re == 0: return await sendMessage(msg,
                                             f'此 `{register_code}` \n兑换码已被使用,是[{used}](tg://user?id={used})的形状了喔')
        
        first = await bot.get_chat(tg1)
        
        # 智能判断处理方式
        if embyid:
            # 用户已有账户 - 执行续期逻辑
            await handle_renewal(session, msg, data, us1, first, tg1, register_code)
        else:
            # 用户无账户 - 执行注册逻辑
            await handle_registration(session, msg, data, us1, first, tg1, register_code)

# 续期处理函数
async def handle_renewal(session, msg, data, us1, first, tg1, register_code):
    embyid = data.embyid
    ex = data.ex
    lv = data.lv
    
    ex_new = datetime.now()
    if ex_new > ex:
        # 账户已过期，从当前时间开始计算
        ex_new = ex_new + timedelta(days=us1)
        await emby.emby_change_policy(id=embyid, method=False)
        if lv == 'c':
            session.query(Emby).filter(Emby.tg == msg.from_user.id).update({Emby.ex: ex_new, Emby.lv: 'b'})
        else:
            session.query(Emby).filter(Emby.tg == msg.from_user.id).update({Emby.ex: ex_new})
        await sendMessage(msg, f'🎊 少年郎，恭喜你，已收到 [{first.first_name}](tg://user?id={tg1}) 的{us1}天🎁\n'
                               f'__已解封账户并延长到期时间至(以当前时间计)__\n到期时间：{ex_new.strftime("%Y-%m-%d %H:%M:%S")}')
    else:
        # 账户未过期，在原有到期时间基础上延长
        ex_new = ex + timedelta(days=us1)
        session.query(Emby).filter(Emby.tg == msg.from_user.id).update({Emby.ex: ex_new})
        await sendMessage(msg,
                          f'🎊 少年郎，恭喜你，已收到 [{first.first_name}](tg://user?id={tg1}) 的{us1}天🎁\n到期时间：{ex_new.strftime("%Y-%m-%d %H:%M:%S")}')
    
    session.commit()
    new_code = register_code[:-7] + "░" * 7
    await sendMessage(msg,
                      f'· 🎟️ 续期码使用 - [{msg.from_user.first_name}](tg://user?id={msg.chat.id}) [{msg.from_user.id}] 使用了 {new_code}\n· 📅 实时到期 - {ex_new}',
                      send=True)
    LOGGER.info(f"【续期码】：{msg.from_user.first_name}[{msg.chat.id}] 使用了 {register_code}，到期时间：{ex_new}")

# 注册处理函数
async def handle_registration(session, msg, data, us1, first, tg1, register_code):
    # 检查是否已有注册资格
    if data.us > 0: 
        return await sendMessage(msg, "已有注册资格，请先使用【创建账户】注册，勿重复使用其他兑换码。")
    
    # 增加注册积分
    x = data.us + us1
    session.query(Emby).filter(Emby.tg == msg.from_user.id).update({Emby.us: x})
    session.commit()
    
    await sendPhoto(msg, photo=bot_photo,
                    caption=f'🎊 少年郎，恭喜你，已经收到了 [{first.first_name}](tg://user?id={tg1}) 发送的邀请注册资格\n\n请选择你的选项~',
                    buttons=register_code_ikb)
    
    new_code = "░" * (len(register_code) - 5) + register_code[-5:]
    await sendMessage(msg,
                      f'· 🎟️ 注册码使用 - [{msg.from_user.first_name}](tg://user?id={msg.chat.id}) [{msg.from_user.id}] 使用了 {new_code}',
                      send=True)
    LOGGER.info(f"【注册码】：{msg.from_user.first_name}[{msg.chat.id}] 使用了 {register_code} - {us1}")
