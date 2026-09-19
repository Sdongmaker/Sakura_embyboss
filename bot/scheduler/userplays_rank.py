import math
import cn2an
from datetime import datetime, timezone, timedelta

from bot import bot, bot_photo, group, LOGGER, ranks
from bot.func_helper.emby import emby, emby_del_all, emby_policy_all
from bot.func_helper.utils import convert_to_beijing_time, convert_s, cache, get_users
from bot.sql_helper import Session
from bot.sql_helper.sql_emby import sql_get_emby, Emby, sql_update_emby
from bot.func_helper.fix_bottons import plays_list_button


class Uplaysinfo:
    client = emby

    @classmethod
    @cache.memoize(ttl=120)
    async def users_playback_list(cls, days):
        try:
            play_list = await emby.emby_cust_commit(emby_id=None, days=days, method='sp')
        except Exception as e:
            print(f"Error fetching playback list: {e}")
            return None, 1

        if play_list is None:
            return None, 1

        with Session() as session:
            # 更高效地查询 Emby 表的数据
            result = session.query(Emby).filter(Emby.name.isnot(None)).all()

            if not result:
                return None, 1

            total_pages = math.ceil(len(play_list) / 10)
            members = await get_users()
            members_dict = {}

            for record in result:
                members_dict[record.name] = {
                    "name": members.get(record.tg, record.name),
                    "tg": record.tg,
                }

            pages_data = []

            for page_number in range(1, total_pages + 1):
                start_index = (page_number - 1) * 10
                end_index = start_index + 10
                page_data = f'**{ranks.logo} {days} 天观影榜**\n\n'

                for rank, play_record in enumerate(play_list[start_index:end_index], start=start_index + 1):
                    member_info = members_dict.get(play_record[0], None)

                    if not member_info or not member_info["tg"]:
                        emby_name = play_record[0] + ' (未绑定Bot)'
                        tg = 'None'
                    else:
                        emby_name = member_info["name"]
                        tg = member_info["tg"]

                    formatted_time = await convert_s(int(play_record[1]))
                    page_data += f'**第{cn2an.an2cn(rank)}名** | [{emby_name}](https://www.google.com/search?q={tg})\n' \
                                 f'  观影时长 | {formatted_time}\n'

                page_data += f'\n#UPlaysRank {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")}'
                pages_data.append(page_data)

            return pages_data, total_pages

    @staticmethod
    async def user_plays_rank(days=7):
        a, n = await Uplaysinfo.users_playback_list(days)
        if not a:
            return await bot.send_photo(chat_id=group[0], photo=bot_photo,
                                        caption=f'获取过去{days}天UserPlays失败，请手动重试')
        play_button = await plays_list_button(n, 1, days)
        await bot.send_photo(chat_id=group[0], photo=bot_photo, caption=a[0], reply_markup=play_button)

    @staticmethod
    async def check_low_activity():
        now = datetime.now(timezone(timedelta(hours=8)))
        success, users = await emby.users()
        if not success:
            return await bot.send_message(chat_id=group[0], text='调用emby api失败')
        from bot import config
        activity_check_days = config.activity_check_days
        msg = f'正在执行**{activity_check_days}天活跃检测**\n'
        for user in users:
            # 数据库先找
            e = sql_get_emby(tg=user["Name"])
            if e is None:
                continue

            elif e.lv == 'c':
                try:
                    ac_date = convert_to_beijing_time(user["LastActivityDate"])
                except KeyError:
                    ac_date = "None"
                finally:
                    if ac_date == "None" or ac_date + timedelta(days=15) < now:
                        if await emby_del_all(tg=e.tg, embyid=e.embyid):
                            sql_update_emby(Emby.embyid == e.embyid, embyid=None, name=None, pwd=None, lv='d',
                                            cr=None, ex=None)
                            msg += f'**活跃检测** - [{e.name}](tg://user?id={e.tg})\n#id{e.tg} 禁用后未解禁，已执行删除。\n\n'
                            LOGGER.info(f"【活跃检测】- 删除账户 {user['Name']} #id{e.tg}")
                        else:
                            msg += f'**活跃检测** - [{e.name}](tg://user?id={e.tg})\n#id{e.tg} 禁用后未解禁，执行删除失败。\n\n'
                            LOGGER.info(f"【活跃检测】- 删除账户失败 {user['Name']} #id{e.tg}")
            elif e.lv == 'b':
                try:
                    ac_date = convert_to_beijing_time(user["LastActivityDate"])
                    
                    # print(e.name, ac_date, now)
                    if ac_date + timedelta(days=activity_check_days) < now:
                        if await emby_policy_all(tg=e.tg, embyid=user["Id"], disable=True):
                            sql_update_emby(Emby.embyid == user["Id"], lv='c')
                            msg += f"**活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} {activity_check_days}天未活跃，禁用\n\n"
                            LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：{activity_check_days}天未活跃")
                        else:
                            msg += f"**活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n{activity_check_days}天未活跃，禁用失败，请检查emby连通性\n\n"
                            LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：禁用失败，请检查emby连通性")
                except KeyError:
                    if await emby_policy_all(tg=e.tg, embyid=user["Id"], disable=True):
                        sql_update_emby(Emby.embyid == user["Id"], lv='c')
                        msg += f"**活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} 注册后未活跃，禁用\n\n"
                        LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：注册后未活跃禁用")
                    else:
                        msg += f"**活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} 注册后未活跃，禁用失败，请检查emby连通性\n\n"
                        LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：禁用失败，请检查emby连通性")
        msg += '**活跃检测结束**\n'
        n = 1000
        chunks = [msg[i:i + n] for i in range(0, len(msg), n)]
        for c in chunks:
            await bot.send_message(chat_id=group[0], text=c + f'**{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
