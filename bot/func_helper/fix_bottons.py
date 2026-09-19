from cacheout import Cache
from pykeyboard import InlineKeyboard, InlineButton
from pyrogram.types import InlineKeyboardMarkup
from pyromod.helpers import ikb, array_chunk
from bot import chanel, main_group, bot_name, tz_id, tz_ad, tz_api, tz_version, tz_username, tz_password, _open, schedall, auto_update, fuxx_pitao, moviepilot, config, LOGGER
from bot.func_helper import nezha_res
from bot.func_helper.emby import emby
from bot.func_helper.utils import members_info

cache = Cache()

def judge_start_ikb(is_admin: bool, account: bool) -> InlineKeyboardMarkup:
    buttons = [['用户功能', 'members'], ['服务器', 'server']] if account else [['复制 TG ID', 'copy_tg_id']]
    if getattr(config.shop, 'url', ''):
        buttons.append(['去商城', config.shop.url, 'url'])
    if account and schedall.check_ex:
        buttons.append(['使用续期码', 'exchange'])
    if account and _open.use_whitelist_code:
        buttons.append(['使用白名单码', 'wl_exchange'])
    if is_admin:
        buttons.append(['管理面板', 'manage'])
    return ikb(buttons)

group_f = ikb([[('点击我', f't.me/{bot_name}', 'url')]])
judge_group_ikb = ikb([[('频道入口', f't.me/{chanel}', 'url'), ('群组入口', f't.me/{main_group}', 'url')], [('关闭消息', 'closeit')]])


def members_ikb(is_admin: bool = False, account: bool = False) -> InlineKeyboardMarkup:
    if not account:
        return judge_start_ikb(is_admin, False)
    buttons = [[('兑换码', 'exchange'), ('删除账号', 'delme')], [('重置密码', 'reset')], [('我的收藏', 'my_favorites'), ('我的设备', 'my_devices')]]
    if moviepilot.status:
        buttons.append([('点播中心', 'download_center')])
    buttons.append([('主界面', 'back_start')])
    return ikb(buttons)

gm_ikb_content = ikb([[('创建续期/白名单码', 'cr_link'), ('兑换设置', 'set_renew')], [('用户列表', 'normaluser'), ('白名单列表', 'whitelist'), ('设备列表', 'user_devices')], [('商城配置', 'shop_panel'), ('主界面', 'back_start'), ('其他', 'back_config')]])

back_start_ikb = ikb([[('回到首页', 'back_start')]])
back_members_ikb = ikb([[('返回', 'members')]])
back_manage_ikb = ikb([[('返回', 'manage')]])
re_changetg_ikb = ikb([[('换绑TG', 'changetg'), ('用户主页', 'members')]])
re_bindtg_ikb = ikb([[('绑定TG', 'bindtg'), ('用户主页', 'members')]])
re_delme_ikb = ikb([[('重试', 'delme')], [('返回', 'members')]])
re_reset_ikb = ikb([[('重试', 'reset')], [('返回', 'members')]])
re_exchange_b_ikb = ikb([[('重试', 'exchange'), ('关闭', 'closeit')]])

def send_changetg_ikb(cr_id, rp_id):
    return ikb([[('通过', f'changetg_{cr_id}_{rp_id}'), ('驳回', f'nochangetg_{cr_id}_{rp_id}')]])

def del_me_ikb(embyid) -> InlineKeyboardMarkup:
    return ikb([[('确定', f'delemby-{embyid}')], [('取消', 'members')]])

@cache.memoize(ttl=120)
async def cr_page_server():
    servers = await nezha_res.sever_info(tz_ad, tz_api, tz_id, tz_version, tz_username, tz_password)
    if not servers:
        return ikb([[('用户', 'members'), ('上一级', 'back_start')]]), None
    buttons = [[item['name'], f"server:{item['id']}"] for item in servers]
    buttons.append([['用户', 'members'], ['上一级', 'back_start']])
    return ikb(buttons), servers

re_cr_link_ikb = ikb([[('继续创建', 'cr_link'), ('返回主页', 'manage')]])
close_it_ikb = ikb([[('Close', 'closeit')]])

def ch_link_ikb(items: list) -> InlineKeyboardMarkup:
    return ikb(array_chunk(items, 2) + [[('回到首页', 'manage')]])

async def cr_paginate(total_page: int, current_page: int, n) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'pagination_keyboard:{number}' + f'_{n}')
    follow_up = [InlineButton('关闭', 'closeit')]
    if total_page > 5:
        if current_page - 5 >= 1:
            follow_up.insert(0, InlineButton('前进5页', f'pagination_keyboard:{current_page - 5}_{n}'))
        if current_page + 5 < total_page:
            follow_up.insert(0, InlineButton('后退5页', f'pagination_keyboard:{current_page + 5}_{n}'))
    keyboard.row(*follow_up)
    return keyboard

async def plays_list_button(total_page: int, current_page: int, days) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'uranks:{number}' + f'_{days}')
    follow_up = [InlineButton('关闭', 'closeit')]
    if total_page > 5:
        if current_page - 5 >= 1:
            follow_up.insert(0, InlineButton('前进5页', f'uranks:{current_page - 5}_{days}'))
        if current_page + 5 < total_page:
            follow_up.insert(0, InlineButton('后退5页', f'uranks:{current_page + 5}_{days}'))
    keyboard.row(*follow_up)
    return keyboard

async def whitelist_page_ikb(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard(); keyboard.paginate(total_page, current_page, 'whitelist:{number}'); keyboard.row(InlineButton('返回', 'manage')); return keyboard

async def normaluser_page_ikb(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard()
    keyboard.paginate(total_page, current_page, 'normaluser:{number}')
    follow_up = [InlineButton('返回', 'manage')]
    if total_page > 5:
        if current_page - 5 >= 1:
            follow_up.insert(0, InlineButton('前进5页', f'normaluser:{current_page - 5}'))
        if current_page + 5 < total_page:
            follow_up.insert(0, InlineButton('后退5页', f'normaluser:{current_page + 5}'))
    keyboard.row(*follow_up)
    return keyboard

def devices_page_ikb(has_prev: bool, has_next: bool, page: int) -> InlineKeyboardMarkup:
    buttons = []
    if has_prev or has_next:
        nav = []
        if has_prev:
            nav.append(('上一页', f'devices:{page - 1}'))
        nav.append((f'第 {page} 页', 'none'))
        if has_next:
            nav.append(('下一页', f'devices:{page + 1}'))
        buttons.append(nav)
    buttons.append([('返回', 'manage')])
    return ikb(buttons)

async def favorites_page_ikb(total_page: int, current_page: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboard(); keyboard.paginate(total_page, current_page, 'page_my_favorites:{number}'); keyboard.row(InlineButton('返回', 'members')); return keyboard

def cr_renew_ikb():
    keyboard = InlineKeyboard(row_width=2)
    keyboard.add(InlineButton(f'续期码: {"开" if _open.exchange else "关"}', 'set_renew-exchange'), InlineButton(f'白名单码: {"开" if _open.use_whitelist_code else "关"}', 'set_renew-use_whitelist_code'))
    keyboard.row(InlineButton('返回', 'manage'))
    return keyboard

def shop_config_ikb() -> InlineKeyboardMarkup:
    return ikb([[('切换启用', 'shop_toggle'), ('重置 API Key', 'shop_reset_key')],
                [('重置 API Secret', 'shop_reset_secret')],
                [('返回', 'manage')]])

def config_preparation() -> InlineKeyboardMarkup:
    mp_set = '已开启' if moviepilot.status else '已关闭'
    auto_up = '已开启' if auto_update.status else '已关闭'
    leave_ban = '已开启' if _open.leave_ban else '已关闭'
    fuxx_pt = '已开启' if fuxx_pitao else '已关闭'
    return ikb([[('导出日志', 'log_out'), ('设置探针', 'set_tz')], [('普通用户线路', 'set_line'), ('白名单线路', 'set_whitelist_line')], [('客户端过滤', 'set_client_filter')], [(f'{leave_ban} 退群封禁', 'leave_ban')], [(f'{auto_up} 自动更新bot', 'set_update'), (f'{mp_set} Moviepilot点播', 'set_mp')], [(f'设置活跃检测天数({config.activity_check_days}天)', 'set_activity_check_days')], [(f'设置封存账号天数({config.freeze_days}天)', 'set_freeze_days')], [('返回', 'manage')]])

back_config_p_ikb = ikb([[('返回主控', 'back_config')]])

def back_set_ikb(method) -> InlineKeyboardMarkup:
    return ikb([[('重新设置', f'{method}'), ('返回主页', 'back_config')]])

def try_set_buy(ls: list) -> InlineKeyboardMarkup:
    return ikb([[ls], [['体验结束返回', 'back_config']]])

def client_filter_panel() -> InlineKeyboardMarkup:
    cf_enabled = '已开启' if config.client_filter_enabled else '已关闭'
    cf_mode_text = '黑名单模式' if config.client_filter_mode == 'blacklist' else '白名单模式'
    return ikb([[(f'客户端过滤({cf_enabled})', 'toggle_client_filter')], [(f'模式({cf_mode_text})', 'set_client_filter_mode')], [('返回', 'back_config')]])

async def cr_kk_ikb(uid, first):
    data = await members_info(uid)
    if data is None:
        return f'**TG**：[{first}](tg://user?id={uid}) [`{uid}`]\n数据库中没有此ID。', ikb([])
    name, lv, ex, embyid = data
    text = f'**TG&名称** | [{first}](tg://user?id={uid})\n**识别ID** | `{uid}`\n**当前状态** | {lv}\n**账号名称** | {name}\n**到期时间** | **{ex}**'
    buttons = []
    if embyid:
        ban = '解除禁用' if lv == '**已禁用**' else '禁用账户'
        buttons = [[ban, f'user_ban-{uid}'], ['删除账户', f'closeemby-{uid}']]
        try:
            result = await emby.emby_cust_commit(emby_id=embyid, days=30)
            text += f"\\n**上次活动** | {result[0][0].split('.')[0]}\\n**过去30天** | {result[0][1]} 分钟"
        except (TypeError, IndexError, ValueError):
            text += '\\n**过去30天未有记录**'
    buttons.extend([['踢出并封禁', f'fuckoff-{uid}'], ['删除消息', 'closeit']])
    return text, ikb(array_chunk(buttons, 2))

def uinfo_ikb(embyid, lv=None):
    rows = []
    if lv == 'c': rows.append([('启用账户', f'uinfo_enable-{embyid}')])
    elif lv in ('a', 'b'): rows.append([('禁用账户', f'uinfo_disable-{embyid}')])
    if lv != 'd': rows.append([('播放查询', f'userip-{embyid}'), ('删除账户', f'uinfo_delete-{embyid}')])
    rows.append([('关闭', 'closeit')]); return ikb(rows)

def uinfo_delete_confirm_ikb(embyid): return ikb([[('确认删除', f'uinfo_delete_confirm-{embyid}'), ('取消', f'uinfo_delete_cancel-{embyid}')]])

def sched_buttons():
    statuses = [('播放日榜', 'dayrank'), ('播放周榜', 'weekrank'), ('观影日榜', 'dayplayrank'), ('观影周榜', 'weekplayrank'), ('到期保号', 'check_ex'), ('活跃保号', 'low_activity'), ('自动备份数据库', 'backup_db')]
    return ikb([[('开' if getattr(schedall, attr) else '关', f'sched-{attr}') for _, attr in statuses], [('返回', 'manage')]])

request_tips_ikb = None

def get_resource_ikb(download_name: str):
    return ikb([[(f'下载本片', f'download_{download_name}'), ('激活订阅', f'submit_{download_name}')], [('关闭', 'closeit')]])

re_download_center_ikb = ikb([[('点播', 'get_resource'), ('下载进度', 'download_rate')], [('返回', 'members')]])
continue_search_ikb = ikb([[('继续搜索', 'continue_search'), ('取消搜索', 'cancel_search')], [('返回', 'download_center')]])

def download_resource_ids_ikb(resource_ids: list):
    rows = []
    for i in range(0, len(resource_ids), 2):
        row = [[f'资源编号: {resource_ids[i]}', f'download_resource_id_{resource_ids[i]}']]
        if i + 1 < len(resource_ids): row.append([f'资源编号: {resource_ids[i + 1]}', f'download_resource_id_{resource_ids[i + 1]}'])
        rows.append(row)
    rows.append([('取消', 'cancel_download')])
    return ikb(rows)

def request_record_page_ikb(has_prev: bool, has_next: bool):
    buttons = []
    if has_prev: buttons.append(('< 上一页', 'request_record_prev'))
    if has_next: buttons.append(('下一页 >', 'request_record_next'))
    return ikb([buttons, [('返回', 'download_center')]])

def mp_search_page_ikb(has_prev: bool, has_next: bool, page: int):
    buttons = []
    if has_prev: buttons.append(('< 上一页', 'mp_search_prev_page'))
    if has_next: buttons.append(('下一页 >', 'mp_search_next_page'))
    return ikb([buttons, [('选择下载', 'mp_search_select_download'), ('取消搜索', 'cancel_search')]])

def mp_config_ikb():
    status = '开' if moviepilot.status else '关'
    lv = {'a': '白名单', 'b': '普通用户'}.get(moviepilot.lv, '无')
    return ikb([[ (f'点播功能: {status}', 'set_mp_status')], [('设置用户权限', 'set_mp_lv')], [('设置日志频道', 'set_mp_log_channel')], [('返回', 'back_config')]])
