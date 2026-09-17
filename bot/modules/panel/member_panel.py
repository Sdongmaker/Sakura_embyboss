"""
用户区面板代码
先检测有无账户
无 -> 创建账户、换绑tg

有 -> 账户续期，重置密码，删除账户，显隐媒体库
"""
import asyncio
import datetime
import math
from datetime import timedelta, datetime
from bot import bot, LOGGER, _open, ranks, group, config, bot_name
from pyrogram import filters
from bot.func_helper.concurrency import get_user_lock
from bot.func_helper.emby import emby, emby_del_all, emby_policy_all, emby_reset_all, render_server_lines
from bot.func_helper.register_queue import get_register_queue_manager, RegisterJob
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.utils import members_info, judge_admins, tem_deluser
from bot.func_helper.fix_bottons import members_ikb, back_members_ikb, del_me_ikb, re_delme_ikb, \
    re_reset_ikb, re_changetg_ikb, emby_block_ikb, user_emby_block_ikb, user_emby_unblock_ikb, re_exchange_b_ikb, \
    re_bindtg_ikb, close_it_ikb, send_changetg_ikb, favorites_page_ikb
from bot.func_helper.msg_utils import callAnswer, editMessage, callListen, sendMessage, ask_return, deleteMessage
from bot.modules.commands import p_start
from bot.modules.commands.partition_code import _redeem_partition_code
from bot.modules.commands.exchange import rgs_code
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby
from bot.sql_helper.sql_emby2 import sql_get_emby2, sql_delete_emby2

# 创号函数
async def create_user(_, call, stats):
    msg = await ask_return(call,
                           text='🤖**注意：您已进入注册状态:\n\n• 请在2min内输入 `[用户名]`\n• 举个例子🌰：`苏苏`**\n\n• 用户名中不限制中/英文/emoji，🚫**特殊字符**'
                                '\n• 账户密码由系统生成并只发送一次，请及时保存；退出请点 /cancel', timer=120,
                           button=close_it_ikb)
    if not msg:
        return

    elif msg.text == '/cancel':
        return await asyncio.gather(msg.delete(), bot.delete_messages(msg.from_user.id, msg.id - 1))

    try:
        emby_name, = msg.text.split()
    except (IndexError, ValueError):
        await msg.reply(f'⚠️ 输入格式错误\n\n`{msg.text}`\n **会话已结束！**')
    else:
        async with get_user_lock(call.from_user.id):
            current = sql_get_emby(tg=call.from_user.id)
            if not current:
                return await msg.reply('⚠️ 数据库没有你，请重新 /start录入')
            if current.embyid:
                return await msg.reply('💦 你已经有账户啦！请勿重复注册。')
            if not stats and int(current.us or 0) <= 0:
                return await msg.reply('🤖 当前没有可用注册资格，请重新领取注册码后再试。')

            days = _open.open_us if stats else int(current.us)
            queue = get_register_queue_manager()
            send = await msg.reply(
                f'🆗 会话结束，收到设置\n\n用户名：**{emby_name}** \n\n__正在加入注册队列__......')
            ok, reason, position = await queue.enqueue(
                RegisterJob(
                    user_id=call.from_user.id,
                    username=emby_name,
                    stats=stats,
                    days=days,
                    status_message=send,
                )
            )
            if ok:
                return await editMessage(
                    send,
                    f'🆗 会话结束，收到设置\n\n用户名：**{emby_name}** \n\n'
                    f'__已进入注册队列，当前排队序号：{position}__\n'
                    f'请耐心等待，创建完成后我会在这里直接通知你。',
                )

            failure_text = {
                "duplicate": "⚠️ 你已经有一个注册任务正在排队或处理中，请勿重复提交。",
                "queue_full": "⚠️ 当前注册排队人数过多，请稍后再试。",
                "slot_full": f'**🚫 很抱歉，剩余可注册总数({_open.tem})，已达总注册限制({_open.all_user})。**',
            }.get(reason, "❌ 注册任务提交失败，请稍后重试。")
            return await editMessage(send, failure_text)


# 键盘中转
@bot.on_callback_query(filters.regex('members'))
async def members(_, call):
    data = await members_info(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    await callAnswer(call, f"✅ 用户界面")
    name, lv, ex, us, embyid = data
    text = f"▎__欢迎进入用户面板！{call.from_user.first_name}__\n\n" \
           f"**· 🆔 用户のID** | `{call.from_user.id}`\n" \
           f"**· 📊 当前状态** | {lv}\n" \
           f"**· ⏳ 剩余天数** | {us}\n" \
           f"**· 💠 账号名称** | [{name}](tg://user?id={call.from_user.id})\n" \
           f"**· 🚨 到期时间** | {ex}"
    if not embyid:
        is_admin = judge_admins(call.from_user.id)
        await editMessage(call, text, members_ikb(is_admin, False))
    else:
        await editMessage(call, text, members_ikb(account=True))


# 创建账户
@bot.on_callback_query(filters.regex('create') & user_in_group_on_filter)
async def create(_, call):
    """

    当队列已满时，用户会收到等待提示。
    信号量和计数器正确释放。
    代码保存至收藏夹，改版时勿忘加入排队机制
    :param _:
    :param call:
    :return:
    """
    stats = None
    queue = get_register_queue_manager()
    if await queue.is_user_busy(call.from_user.id):
        return await callAnswer(call, '⚠️ 你已有注册任务正在排队或处理中，请稍后。', True)

    async with get_user_lock(call.from_user.id):
        e = sql_get_emby(tg=call.from_user.id)
        if not e:
            return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)

        if e.embyid:
            return await callAnswer(call, '💦 你已经有账户啦！请勿重复注册。', True)
        if _open.stat:
            stats = True
        elif int(e.us or 0) > 0:
            stats = False
        else:
            return await callAnswer(call, f'🤖 自助注册已关闭，等待开启或使用注册码注册。', True)

    if stats:
        send = await callAnswer(call, f"🪙 开放注册中，免除资质核验。", True)
    else:
        send = await callAnswer(call, f'🪙 资质核验成功，请稍后。', True)

    if send is False:
        return
    await create_user(_, call, stats=stats)


# 换绑tg
@bot.on_callback_query(filters.regex('changetg') & user_in_group_on_filter)
async def change_tg(_, call):
    try:
        status, current_id_str, replace_id_str = call.data.split('_')
        if not judge_admins(call.from_user.id): return await callAnswer(call, '⚠️ 你什么档次？', True)
        current_id = int(current_id_str)
        replace_id = int(replace_id_str)
        if status == 'nochangetg':
            return await asyncio.gather(
                editMessage(call,
                            f' ❎ 好的，[您](tg://user?id={call.from_user.id})已拒绝[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。'),
                bot.send_message(current_id, '❌ 您的换绑请求已被拒。请在群组中详细说明情况。'))

        await editMessage(call,
                          f' ✅ 好的，[您](tg://user?id={call.from_user.id})已通过[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。')
        e = sql_get_emby(tg=replace_id)
        if not e or not e.embyid: return await bot.send_message(current_id, '⁉️ 出错了，您所换绑账户已不存在。')

        # 清空原账号信息但保留tg
        if sql_update_emby(Emby.tg == replace_id, embyid=None, name=None, pwd=None,
                          lv='d', cr=None, ex=None, us=0, ch=None):
            LOGGER.info(f'【TG改绑】清空原账户 id{e.tg} 成功')
        else:
            await bot.send_message(current_id, "🍰 **⭕#TG改绑 原账户清空错误，请联系闺蜜（管理）！**")
            LOGGER.error(f"【TG改绑】清空原账户 id{e.tg} 失败, Emby:{e.name}未转移...")
            return

        if sql_update_emby(Emby.tg == current_id, embyid=e.embyid, name=e.name, pwd=e.pwd,
                           lv=e.lv, cr=e.cr, ex=e.ex):
            text = f'⭕ 请接收您的信息！\n\n' \
                   f'· 用户名称 | `{e.name}`\n' \
                   f'· 用户密码 | `{e.pwd}`\n' \
                   f'· 到期时间 | `{e.ex}`\n\n' \
                   f'· 当前线路：\n{render_server_lines(current_id, e.lv, e.embyid)}\n\n' \
                   f'**·在【服务器】按钮 - 查看线路和密码**'
            await bot.send_message(current_id, text)
            LOGGER.info(
                f'【TG改绑】 emby账户 {e.name} 绑定至 {current_id}')
        else:
            await bot.send_message(current_id, '🍰 **【TG改绑】数据库处理出错，请联系闺蜜（管理）！**')
            LOGGER.error(f"【TG改绑】 emby账户{e.name} 绑定未知错误。")
        return
    except (IndexError, ValueError):
        pass
    d = sql_get_emby(tg=call.from_user.id)
    if not d:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if d.embyid:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)

    await callAnswer(call, '⚖️ 更换绑定的TG')
    send = await editMessage(call,
                             '🔰 **【更换绑定emby的tg】**\n'
                             '须知：\n'
                             '- **请确保您之前用其他tg账户注册过**\n'
                             '- **请确保您注册的其他tg账户呈已注销状态**\n'
                             '- **请确保输入正确的emby用户名，安全码/密码**\n\n'
                             '您有120s回复 `[emby用户名] [安全码/密码]`\n例如 `苏苏 5210` ，若密码为空则填写"None"，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【`{m.text}`】\n **会话已结束！**', re_changetg_ikb)

        pwd = '空（直接回车）', 5210 if emby_pwd == 'None' else emby_pwd, emby_pwd
        e = sql_get_emby(tg=emby_name)
        if e is None:
            # 在emby2中，验证安全码 或者密码
            e2 = sql_get_emby2(name=emby_name)
            if e2 is None:
                return await editMessage(call, f'❓ 未查询到bot数据中名为 {emby_name} 的账户，请使用 **绑定TG** 功能。',
                                         buttons=re_bindtg_ikb)
            if emby_pwd != e2.pwd:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n{emby_name} {emby_pwd} 是否正确。',
                                             buttons=re_changetg_ikb)
                sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=e2.name, pwd=emby_pwd,
                                lv=e2.lv, cr=e2.cr, ex=e2.ex)
                sql_delete_emby2(embyid=e2.embyid)
                text = f'⭕ 账户 {emby_name} 的密码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | `{pwd[0]}`\n' \
                       f'· 到期时间 | `{e2.ex}`\n\n' \
                       f'· 当前线路：\n{render_server_lines(call.from_user.id, e2.lv, embyid)}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

            elif emby_pwd == e2.pwd:
                text = f'⭕ 账户 {emby_name} 的安全码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | `{e2.pwd}`\n' \
                       f'· 到期时间 | `{e2.ex}`\n\n' \
                       f'· 当前线路：\n{render_server_lines(call.from_user.id, e2.lv, e2.embyid)}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                sql_update_emby(Emby.tg == call.from_user.id, embyid=e2.embyid, name=e2.name, pwd=e2.pwd,
                                lv=e2.lv, cr=e2.cr, ex=e2.ex)
                sql_delete_emby2(embyid=e2.embyid)
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

        else:
            if call.from_user.id == e.tg: return await editMessage(call, '⚠️ 您已经拥有账户。')
            if emby_pwd != e.pwd:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n{emby_name} {emby_pwd} 是否正确。',
                                             buttons=re_changetg_ikb)
            await  asyncio.gather(editMessage(call,
                                              f'✔️ 会话结束，验证成功\n\n'
                                              f'🔰 用户名：**{emby_name}** 输入码：**{emby_pwd}**......\n\n'
                                              f'🎯 已向授权群发送申请，请联系并等待管理员确认......'),
                                  sendMessage(call,
                                              f'⭕#TG改绑\n'
                                              f'**用户 [{call.from_user.id}](tg://user?id={call.from_user.id}) 正在试图改绑Emby: [{e.name}](tg://user?id={e.tg})，原TG: `{e.tg}`，已通过安全/密码核验\n\n'
                                              f'请管理员审核决定：**',
                                              buttons=send_changetg_ikb(call.from_user.id, e.tg),
                                              send=True))
            LOGGER.info(
                f'【TG改绑】 {call.from_user.first_name}-{call.from_user.id} 通过验证账户，已递交对Emby: {emby_name}, Tg:{e.tg} 的换绑申请')


@bot.on_callback_query(filters.regex('bindtg') & user_in_group_on_filter)
async def bind_tg(_, call):
    d = sql_get_emby(tg=call.from_user.id)
    if d is not None and d.embyid is not None:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)
    await callAnswer(call, '⚖️ 将账户绑定TG')
    send = await editMessage(call,
                             '🔰 **【已有emby绑定至tg】**\n'
                             '须知：\n'
                             '- **请确保您需绑定的账户不在bot中**\n'
                             '- **请确保您不是恶意绑定他人的账户**\n'
                             '- **请确保输入正确的emby用户名，密码**\n\n'
                             '您有120s回复 `[emby用户名] [密码]`\n例如 `苏苏 5210` ，若密码为空则填写“None”，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【`{m.text}`】\n **会话已结束！**', re_bindtg_ikb)
        await editMessage(call,
                          f'✔️ 会话结束，收到设置\n\n用户名：**{emby_name}** 正在检查密码 **{emby_pwd}**......')
        e = sql_get_emby(tg=emby_name)
        if e is None:
            e2 = sql_get_emby2(name=emby_name)
            if e2 is None:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'🍥 很遗憾绑定失败，您输入的账户密码不符（{emby_name} - {emby_pwd}），请仔细确认后再次尝试',
                                             buttons=re_bindtg_ikb)
                else:
                    pwd_text = '空（直接回车）' if emby_pwd == 'None' else emby_pwd
                    ex = (datetime.now() + timedelta(days=30))
                    text = f'✅ 账户 {emby_name} 成功绑定\n\n' \
                           f'· 用户名称 | `{emby_name}`\n' \
                           f'· 用户密码 | `{pwd_text}`\n' \
                           f'· 到期时间 | `{ex}`\n\n' \
                           f'· 当前线路：\n{render_server_lines(call.from_user.id, "b", embyid)}\n\n' \
                           f'· **在【服务器】按钮 - 查看线路和密码**'
                    sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=emby_name, pwd=pwd_text,
                                    lv='b', cr=datetime.now(), ex=ex)
                    await editMessage(call, text)
                    await sendMessage(call,
                                      f'⭕#新TG绑定 原emby账户 #{emby_name} \n\n已绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                      send=True)
                    LOGGER.info(
                        f'【新TG绑定】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
            else:
                await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)
        else:
            await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)


# kill yourself
@bot.on_callback_query(filters.regex('delme'))
async def del_me(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    else:
        if e.embyid is None:
            return await callAnswer(call, '未查询到账户，不许乱点！💢', True)
        await callAnswer(call, "🔴 请先进行 密码 验证")
        edt = await editMessage(call, '**🔰账户安全验证**：\n\n👮🏻验证是否本人进行敏感操作，请对我发送您的账号密码。倒计时 120s\n'
                                      '🛑 **停止请点 /cancel**')
        if edt is False:
            return

        m = await callListen(call, 120)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            factor = (e.pwd or '').strip()
            if factor and m.text.strip() != factor:
                await m.delete()
                await editMessage(call, '**💢 验证不通过，密码错误。**', re_delme_ikb)
            else:
                await m.delete()
                await editMessage(call, '**⚠️ 如果您的账户到期，我们将封存您的账户，但仍保留数据'
                                        '而如果您选择删除，这意味着服务器会将您此前的活动数据全部删除。\n**',
                                  buttons=del_me_ikb(e.embyid))


@bot.on_callback_query(filters.regex('delemby'))
async def del_emby(_, call):
    send = await callAnswer(call, "🎯 get，正在删除ing。。。")
    if send is False:
        return

    embyid = call.data.split('-')[1]
    if await emby_del_all(tg=call.from_user.id, embyid=embyid):
        sql_update_emby(Emby.embyid == embyid, embyid=None, name=None, pwd=None, lv='d', cr=None, ex=None)
        tem_deluser()
        send1 = await editMessage(call, '🗑️ 好了，已经为您删除...\n愿来日各自安好，山高水长，我们有缘再见！',
                                  buttons=back_members_ikb)
        if send1 is False:
            return

        LOGGER.info(f"【删除账号】：{call.from_user.id} 已删除！")
    else:
        await editMessage(call, '🥧 蛋糕辣~ 好像哪里出问题了，请向管理反应', buttons=back_members_ikb)
        LOGGER.error(f"【删除账号】：{call.from_user.id} 失败！")


# 重置密码为空密码
@bot.on_callback_query(filters.regex('reset'))
async def reset(_, call):
    e = sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if e.embyid is None:
        return await bot.answer_callback_query(call.id, '未查询到账户，不许乱点！💢', show_alert=True)
    else:
        await callAnswer(call, "🔴 请先进行 密码 验证")
        send = await editMessage(call, '**🔰账户安全验证**：\n\n 👮🏻验证是否本人进行敏感操作，请对我发送您的账号密码。倒计时 120 s\n'
                                       '🛑 **停止请点 /cancel**')
        if send is False:
            return

        m = await callListen(call, 120, buttons=back_members_ikb)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            factor = (e.pwd or '').strip()
            if factor and m.text.strip() != factor:
                await m.delete()
                await editMessage(call, f'**💢 验证不通过，{m.text} 密码错误。**', buttons=re_reset_ikb)
            else:
                await m.delete()
                await editMessage(call, '🎯 请在 120s内 输入你要更新的密码,不限制中英文，emoji。特殊字符部分支持，其他概不负责。\n\n'
                                        '点击 /cancel 将重置为空密码并退出。 无更改退出状态请等待120s')
                mima = await callListen(call, 120, buttons=back_members_ikb)
                if mima is False:
                    return

                elif mima.text == '/cancel':
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby_reset_all(tg=call.from_user.id, embyid=e.embyid) is True:
                        await editMessage(call, '🕶️ 操作完成！已为您重置密码为 空。', buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了空密码！")
                    else:
                        await editMessage(call, '🫥 重置密码操作失败！请联系管理员。')
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")

                else:
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby_reset_all(tg=call.from_user.id, embyid=e.embyid, new_password=mima.text) is True:
                        await editMessage(call, f'🕶️ 操作完成！已为您重置密码为 `{mima.text}`。',
                                          buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了密码为 {mima.text} ！")
                    else:
                        await editMessage(call, '🫥 操作失败！请联系管理员。', buttons=back_members_ikb)
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")


# 显示/隐藏某些库
@bot.on_callback_query(filters.regex('embyblock'))
async def embyblocks(_, call):
    data = sql_get_emby(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if data.embyid is None:
        return await callAnswer(call, '❓ 未查询到账户，不许乱点!', True)
    elif data.lv == "c":
        return await callAnswer(call, '💢 账户到期，封禁中无法使用！', True)
    elif len(config.emby_block) == 0:
        send = await editMessage(call, '⭕ 管理员未设置。。。 快催催\no(*////▽////*)q', buttons=back_members_ikb)
        if send is False:
            return
    else:
        success, rep = await emby.user(emby_id=data.embyid)
        try:
            if success is False:
                stat = '💨 未知'
            else:
                # 新版本使用 EnabledFolders 和 EnableAllFolders 控制访问
                policy = rep.get("Policy", {})
                enable_all_folders = policy.get("EnableAllFolders")
                enabled_folders = policy.get("EnabledFolders", [])

                if enable_all_folders:
                    # 如果启用所有文件夹，检查是否有特定的阻止设置
                    stat = '🟢 显示'
                else:
                    # 检查目标媒体库是否在启用列表中
                    # 需要获取媒体库ID来进行比较
                    target_folder_ids = await emby.get_folder_ids_by_names(config.emby_block)
                    if target_folder_ids and any(folder_id in enabled_folders for folder_id in target_folder_ids):
                        stat = '🟢 显示'
                    else:
                        stat = '🔴 隐藏'
        except KeyError:
            stat = '💨 未知'
        block = ", ".join(config.emby_block)
        await asyncio.gather(callAnswer(call, "✅ 到位"),
                             editMessage(call,
                                         f'🤺 用户状态：{stat}\n🎬 目前设定的库为: \n\n**{block}**\n\n请选择你的操作。',
                                         buttons=emby_block_ikb(data.embyid)))


# 隐藏
@bot.on_callback_query(filters.regex('emby_block'))
async def user_emby_block(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您关闭显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的隐藏媒体库方法
            re = await emby.hide_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴隐藏好了！ ', buttons=user_emby_block_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"隐藏媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)


# 显示
@bot.on_callback_query(filters.regex('emby_unblock'))
async def user_emby_unblock(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您开启显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的显示媒体库方法
            re = await emby.show_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴显示好了！ ', buttons=user_emby_unblock_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"显示媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)


@bot.on_callback_query(filters.regex('^exchange$') & user_in_group_on_filter)
async def call_exchange(_, call):
    await asyncio.gather(callAnswer(call, '🔋 使用注册/续期码'), deleteMessage(call))
    msg = await ask_return(call, text='🔋 **【使用注册/续期码】**：\n\n'
                                      f'- 请在120s内对我发送你的注册/续期码，形如\n`{ranks.logo}-xx-xxxx`\n退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    elif msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
    else:
        await rgs_code(_, msg, register_code=msg.text)


@bot.on_callback_query(filters.regex('^partitioncode$') & user_in_group_on_filter)
async def call_partition_code(_, call):
    await asyncio.gather(callAnswer(call, '🎟️ 使用分区码'), deleteMessage(call))
    msg = await ask_return(call, text='🎟️ **【使用分区码】**：\n\n- 请在120s内发送分区码\n- 退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    if msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
        return

    ok, text = await _redeem_partition_code(msg.text.strip(), call.from_user.id)
    await asyncio.gather(msg.delete(), sendMessage(call, text, timer=120 if ok else 60))


@bot.on_callback_query(filters.regex('^wl_exchange$') & user_in_group_on_filter)
async def call_wl_exchange(_, call):
    if not _open.use_whitelist_code:
        return await callAnswer(call, '❌ 管理员未开启白名单码功能', True)
    await asyncio.gather(callAnswer(call, '🔑 使用白名单激活码'), deleteMessage(call))
    msg = await ask_return(call, text='🔑 **【使用白名单激活码】**：\n\n'
                                      f'- 请在120s内发送白名单激活码，形如\n`{ranks.logo}-Whitelist_xxxx`\n退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    elif msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
    else:
        await rgs_code(_, msg, register_code=msg.text)


@bot.on_callback_query(filters.regex('^my_favorites|^page_my_favorites:'))
async def my_favorite(_, call):
    # 获取页码
    if call.data == 'my_favorites':
        page = 1
        await callAnswer(call, '🔍 我的收藏')
    else:
        page = int(call.data.split(':')[1])
        await callAnswer(call, f'🔍 打开第{page}页')
    get_emby = sql_get_emby(tg=call.from_user.id)
    if get_emby is None:
        return await callAnswer(call, '您还没有Emby账户', True)
    limit = 10
    start_index = (page - 1) * limit
    favorites = await emby.get_favorite_items(emby_id=get_emby.embyid, start_index=start_index, limit=limit)
    text = "**我的收藏**\n\n"
    for item in favorites.get("Items", []):
        item_id = item.get("Id")
        if not item_id:
            continue
        # 获取项目名称
        item_name = item.get("Name", "")
        item_type = item.get('Type', '未知')
        if item_type == 'Movie':
            item_type = '电影'
        elif item_type == 'Series':
            item_type = '剧集'
        elif item_type == 'Episode':
            item_type = '剧集'
        elif item_type == 'Person':
            item_type = '演员'
        elif item_type == 'Photo':
            item_type = '图片'
        text += f"{item_type}：{item_name}\n"

    total_favorites = favorites.get("TotalRecordCount", 0)
    total_pages = math.ceil(total_favorites / limit)
    keyboard = await favorites_page_ikb(total_pages, page)
    await editMessage(call, text, buttons=keyboard)
@bot.on_callback_query(filters.regex('my_devices'))
async def my_devices(_, call):
    get_emby = sql_get_emby(tg=call.from_user.id)
    if get_emby is None:
        return await callAnswer(call, '您还没有Emby账户', True)
    success, result = await emby.get_emby_userip(emby_id=get_emby.embyid)
    if not success or len(result) == 0:
        return await callAnswer(call, '您好像没播放信息吖')
    else:
        await callAnswer(call, '🔍 正在获取您的设备信息')
        device_count = 0
        ip_count = 0
        device_list = []
        ip_list = []
        device_details = ""
        ip_details = ""
        for r in result:
            device, client, ip = r
            # 统计ip
            if ip not in ip_list:
                ip_count += 1
                ip_list.append(ip)
                ip_details += f'{ip_count}: `{ip}`\n'
            # 统计设备并拼接详情
            if device + client not in device_list:
                device_count += 1
                device_list.append(device + client)
                device_details += f'{device_count}: {device} | {client}  \n'
        text = '**🌏 以下为您播放过的设备&ip 共{}个设备，{}个ip：**\n\n'.format(device_count, ip_count) + '**设备:**\n' + device_details + '**IP:**\n'+ ip_details

        # 以\n分割文本，每20条发送一个消息
        messages = text.split('\n')
        # 每20条消息组成一组
        for i in range(0, len(messages), 20):
            chunk = messages[i:i+20]
            chunk_text = '\n'.join(chunk)
            if not chunk_text.strip():
                continue
            await sendMessage(call.message, chunk_text, buttons=close_it_ikb)
