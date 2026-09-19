"""
定时检测账户有无过期
"""
from datetime import timedelta, datetime

from pyrogram.errors import FloodWait
from sqlalchemy import and_
from asyncio import sleep
from bot import bot, group, LOGGER, config
from bot.func_helper.emby import emby_policy_all, emby_del_all
from bot.sql_helper.sql_emby import Emby, get_all_emby, sql_update_emby
from bot.sql_helper.sql_emby2 import get_all_emby2, Emby2, sql_update_emby2


async def check_expired():
    """Disable expired TG accounts and remove accounts after the freeze period."""
    now = datetime.now()
    rst = get_all_emby(and_(Emby.ex < now, Emby.lv == 'b'))
    if rst:
        for r in rst:
            if await emby_policy_all(tg=r.tg, embyid=r.embyid, disable=True):
                dead_day = r.ex + timedelta(days=config.freeze_days)
                updated = sql_update_emby(Emby.tg == r.tg, lv='c')
                text = (f'【到期检测】\n#id{r.tg} 到期禁用 [{r.name}](tg://user?id={r.tg})\n'
                        f'将封存至 {dead_day.strftime("%Y-%m-%d")}，请及时续期') if updated else \
                       f'【到期检测】\n#id{r.tg} 到期禁用 [{r.name}](tg://user?id={r.tg}) 已禁用，数据库写入失败'
            else:
                text = f'【到期检测】\n#id{r.tg} 到期禁用 [{r.name}](tg://user?id={r.tg}) embyapi操作失败'
            try:
                send = await bot.send_message(r.tg, text)
                await send.forward(group[0])
            except FloodWait as f:
                await sleep(f.value * 1.2)
                send = await bot.send_message(r.tg, text)
                await send.forward(group[0])
            except Exception as e:
                LOGGER.error(e)

    rsc = get_all_emby(and_(Emby.ex < now, Emby.lv == 'c'))
    if rsc:
        for c in rsc:
            delete_day = c.ex + timedelta(days=config.freeze_days)
            if now < delete_day:
                continue
            if await emby_del_all(tg=c.tg, embyid=c.embyid):
                sql_update_emby(Emby.tg == c.tg, embyid=None, name=None, pwd=None, lv='d', cr=None, ex=None)
                text = f'【到期检测】\n#id{c.tg} 删除账户 [{c.name}](tg://user?id={c.tg})\n已到期 {config.freeze_days} 天，执行清除任务'
            else:
                text = f'【到期检测】\n#id{c.tg} #删除账户 [{c.name}](tg://user?id={c.tg})\n到期删除失败，请检查以免无法进行后续使用'
            try:
                send = await bot.send_message(c.tg, text)
                await send.forward(group[0])
            except FloodWait as f:
                await sleep(f.value * 1.2)
                send = await bot.send_message(c.tg, text)
                await send.forward(group[0])
            except Exception as e:
                LOGGER.error(e)

    await _check_expired_emby2()


async def _check_expired_emby2():
    rows = get_all_emby2(and_(Emby2.lv == 'b', Emby2.expired == 0, Emby2.ex < datetime.now()))
    if not rows:
        return LOGGER.info('【封禁检测】- emby2 无数据，跳过')
    for account in rows:
        if await emby_policy_all(embyid=account.embyid, disable=True):
            if sql_update_emby2(Emby2.embyid == account.embyid, expired=1, lv='c'):
                text = f"【封禁检测】- 到期封禁非TG账户 [{account.name}](google.com?q={account.embyid}) 完成"
            else:
                text = f'【封禁检测】- 到期封禁非TG账户：`{account.name}` 数据库更改失败'
        else:
            text = f'【封禁检测】- 到期封禁非TG账户：`{account.name}` embyapi操作失败，请手动处理'
        try:
            await bot.send_message(group[0], text)
        except FloodWait as f:
            await sleep(f.value * 1.2)
            await bot.send_message(group[0], text)
        except Exception as e:
            LOGGER.error(e)
