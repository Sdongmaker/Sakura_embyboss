"""Administrator dashboard and renewal/whitelist code management."""
from pyrogram import filters

from bot import bot, _open, save_config, LOGGER, bot_name, owner
from bot.func_helper.filters import admins_on_filter
from bot.func_helper.fix_bottons import gm_ikb_content, re_cr_link_ikb, close_it_ikb, cr_renew_ikb
from bot.func_helper.msg_utils import callAnswer, editMessage, callListen, sendMessage
from bot.func_helper.utils import create_renew_codes, create_whitelist_codes
from bot.sql_helper.sql_emby import sql_count_emby


@bot.on_callback_query(filters.regex('^manage$') & admins_on_filter)
async def gm_ikb(_, call):
    await callAnswer(call, 'manage面板')
    tg, emby, white = sql_count_emby()
    await editMessage(
        call,
        f'管理员 {call.from_user.first_name}\\n\\n'
        f'· 已注册人数 | **{emby}** • WL **{white}**\\n'
        f'· bot使用人数 | {tg}',
        buttons=gm_ikb_content,
    )


@bot.on_callback_query(filters.regex('^cr_link$') & admins_on_filter)
async def cr_link(_, call):
    await callAnswer(call, '创建续期码/白名单码')
    prompt = (
        '请回复创建 [天数] [数量] [模式] [类型]\\n\\n'
        '**模式**：link - 深链接 | code - 兑换码\\n'
        '**类型**：T - 续期码，W - 白名单码\\n'
        '**续期码**：`90 2 code T`\\n'
        '**白名单码**：`5 code W`\\n\\n'
        '__取消本次操作，请 /cancel__'
    )
    if await editMessage(call, prompt, buttons=re_cr_link_ikb) is False:
        return
    content = await callListen(call, 120, buttons=re_cr_link_ikb)
    if content is False:
        return
    if content.text.strip() == '/cancel':
        await content.delete()
        return await editMessage(call, '您已经取消操作了。', buttons=re_cr_link_ikb)
    try:
        parts = content.text.split()
        if len(parts) == 4:
            days, count, method, kind = int(parts[0]), int(parts[1]), parts[2].lower(), parts[3].lower()
            if kind not in ('t', 'renew', '续期', '续期码') or days <= 0:
                raise ValueError
            links = await create_renew_codes(call.from_user.id, days, count, days, method)
            label = f'{days}天续期码'
        elif len(parts) == 3:
            count, method, kind = int(parts[0]), parts[1].lower(), parts[2].lower()
            if kind not in ('w', 'whitelist', 'wl', '白名单', '白名单码') or count <= 0:
                raise ValueError
            links = await create_whitelist_codes(call.from_user.id, count, method)
            label = '白名单码'
        else:
            raise ValueError
    except (TypeError, ValueError):
        await content.delete()
        return await editMessage(call, '格式错误，仅支持续期码或白名单码。', buttons=re_cr_link_ikb)
    await content.delete()
    if links is None:
        return await editMessage(call, '数据库插入失败，请检查数据库。', buttons=re_cr_link_ikb)
    text = f'{bot_name}已生成 **{label}**\\n\\n{links}'
    for offset in range(0, len(text), 4096):
        await sendMessage(content, text[offset:offset + 4096], buttons=close_it_ikb)
    await editMessage(call, f'{bot_name}已生成 {label}', buttons=re_cr_link_ikb)
    LOGGER.info('管理员 %s 生成了 %s', call.from_user.id, label)


@bot.on_callback_query(filters.regex(r'^set_renew(?:-.+)?$') & admins_on_filter)
async def set_renew(_, call):
    try:
        method = call.data.split('-', 1)[1]
        if method not in ('exchange', 'use_whitelist_code'):
            raise ValueError
        setattr(_open, method, not getattr(_open, method))
        save_config()
    except (IndexError, ValueError):
        pass
    await callAnswer(call, '续期设置已更新')
    await editMessage(call, '关于用户组的续期功能', buttons=cr_renew_ikb())
