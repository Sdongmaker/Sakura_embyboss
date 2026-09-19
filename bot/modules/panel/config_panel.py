"""
可调节设置
此处为控制面板2，主要是为了在bot中能够设置一些变量
部分目前有 导出日志，更改探针，更改emby线路，设置购买按钮

"""
from datetime import datetime

from bot import bot, prefixes, bot_photo, Now, LOGGER, config, save_config, _open, auto_update, moviepilot
from pyrogram import filters

from bot.func_helper.filters import admins_on_filter
from bot.func_helper.fix_bottons import config_preparation, close_it_ikb, back_config_p_ikb, back_set_ikb, mp_config_ikb, client_filter_panel, shop_config_ikb
from bot.func_helper.msg_utils import deleteMessage, editMessage, callAnswer, callListen, sendPhoto, sendFile
from bot.func_helper.scheduler import scheduler
from bot.scheduler.sync_mp_download import sync_download_tasks
from pyromod.helpers import ikb
import secrets

def _shop_panel_text() -> str:
    shop = config.shop
    return (f'**商城上游配置**\n\n状态：`{"已启用" if shop.enabled else "已停用"}`\n'
            f'监听：`{shop.listen_host}:{shop.listen_port}`\n'
            f'站点：`{shop.site_name}`\n'
            f'API Key：`{shop.api_key}`\n'
            f'API Secret：`{shop.api_secret}`\n'
            f'商城地址：`{shop.url or "未设置"}`')

@bot.on_callback_query(filters.regex('^shop_panel$') & admins_on_filter)
async def shop_panel(_, call):
    await callAnswer(call, '商城配置')
    await editMessage(call, _shop_panel_text(), buttons=shop_config_ikb())

@bot.on_callback_query(filters.regex('^shop_toggle$') & admins_on_filter)
async def shop_toggle(_, call):
    config.shop.enabled = not config.shop.enabled
    save_config()
    await callAnswer(call, '商城状态已更新', True)
    await shop_panel(_, call)

@bot.on_callback_query(filters.regex('^shop_reset_key$') & admins_on_filter)
async def shop_reset_key(_, call):
    config.shop.api_key = secrets.token_urlsafe(24)
    save_config()
    await callAnswer(call, 'API Key 已重置', True)
    await shop_panel(_, call)

@bot.on_callback_query(filters.regex('^shop_reset_secret$') & admins_on_filter)
async def shop_reset_secret(_, call):
    config.shop.api_secret = secrets.token_urlsafe(48)
    save_config()
    await callAnswer(call, 'API Secret 已重置', True)
    await shop_panel(_, call)



@bot.on_message(filters.command('config', prefixes=prefixes) & admins_on_filter)
async def config_p_set(_, msg):
    await deleteMessage(msg)
    await sendPhoto(msg, photo=bot_photo, caption="点击你要修改的内容。",
                    buttons=config_preparation())



@bot.on_callback_query(filters.regex('back_config') & admins_on_filter)
async def config_p_re(_, call):
    await callAnswer(call, "config")
    await editMessage(call, "点击你要修改的内容。", buttons=config_preparation())


@bot.on_callback_query(filters.regex("log_out") & admins_on_filter)
async def log_out(_, call):
    await callAnswer(call, '查询中...')
    # file位置以main.py为准
    send = await sendFile(call, file=f"log/log_{Now:%Y%m%d}.txt", file_name=f'log_{Now:%Y-%m-%d}.txt',
                          caption="**导出日志成功！**", buttons=close_it_ikb)
    if send is not True:
        return LOGGER.info(f"【admin】：{call.from_user.id} - 导出日志失败！")

    LOGGER.info(f"【admin】：{call.from_user.id} - 导出日志成功！")


@bot.on_callback_query(filters.regex("set_tz$") & admins_on_filter)
async def set_tz(_, call):
    """显示探针设置菜单"""
    from pyromod.helpers import ikb
    await callAnswer(call, '设置探针')
    
    v0_status = '已开启' if config.tz_version == 'v0' else '已关闭'
    v1_status = '已开启' if config.tz_version == 'v1' else '已关闭'
    komari_status = '已开启' if config.tz_version == 'komari' else '已关闭'
    
    keyboard = ikb([
        [(f'{v0_status} Nezha V0', 'set_tz_version_v0'), (f'{v1_status} Nezha V1', 'set_tz_version_v1')],
        [(f'{komari_status} Komari', 'set_tz_version_komari')],
        [('设置探针参数', 'set_tz_params')],
        [('返回', 'back_config')]
    ])
    
    version_map = {
        'v0': "Nezha V0 (Token认证)",
        'v1': "Nezha V1 (用户名密码认证)",
        'komari': "Komari (API Key认证)"
    }
    version_info = version_map.get(config.tz_version, "Nezha V0 (Token认证)")
    text = f"**探针设置**\n\n" \
           f"当前API版本：**{version_info}**\n" \
           f"探针地址：`{config.tz_ad or '未设置'}`\n"
    
    if config.tz_version == 'v0':
        text += f"API Token：`{config.tz_api[:10] + '...' if config.tz_api and len(config.tz_api) > 10 else config.tz_api or '未设置'}`\n"
    elif config.tz_version == 'v1':
        text += f"用户名：`{config.tz_username or '未设置'}`\n"
    elif config.tz_version == 'komari':
        text += f"API Key：`{config.tz_api[:10] + '...' if config.tz_api and len(config.tz_api) > 10 else config.tz_api or '未设置 (公开接口可不填)'}`\n"
    
    text += f"监控的节点ID：`{config.tz_id or '未设置'}`"
    
    await editMessage(call, text, buttons=keyboard)


@bot.on_callback_query(filters.regex("set_tz_version_v0") & admins_on_filter)
async def set_tz_version_v0(_, call):
    """设置使用 Nezha V0 API"""
    config.tz_version = 'v0'
    save_config()
    await callAnswer(call, '已切换到 Nezha V0 API (Token认证)', True)
    LOGGER.info(f"【admin】：{call.from_user.id} - 切换探针API版本为 Nezha V0")
    await set_tz(_, call)


@bot.on_callback_query(filters.regex("set_tz_version_v1") & admins_on_filter)
async def set_tz_version_v1(_, call):
    """设置使用 Nezha V1 API"""
    config.tz_version = 'v1'
    save_config()
    await callAnswer(call, '已切换到 Nezha V1 API (用户名密码认证)', True)
    LOGGER.info(f"【admin】：{call.from_user.id} - 切换探针API版本为 Nezha V1")
    await set_tz(_, call)


@bot.on_callback_query(filters.regex("set_tz_version_komari") & admins_on_filter)
async def set_tz_version_komari(_, call):
    """设置使用 Komari API"""
    config.tz_version = 'komari'
    save_config()
    await callAnswer(call, '已切换到 Komari 探针', True)
    LOGGER.info(f"【admin】：{call.from_user.id} - 切换探针API版本为 Komari")
    await set_tz(_, call)


@bot.on_callback_query(filters.regex("set_tz_params") & admins_on_filter)
async def set_tz_params(_, call):
    """设置探针参数"""
    await callAnswer(call, '设置探针参数')
    
    if config.tz_version == 'v0':
        prompt = "【设置 Nezha V0 探针】\n\n请输入探针地址，API Token，设置的检测多个id 如：\n" \
                 "**https://tz.example.com\nxxxxxx\n1 2 3**\n" \
                 "（留空ID则显示所有服务器）\n取消点击 /cancel"
    elif config.tz_version == 'v1':
        prompt = "【设置 Nezha V1 探针】\n\n请依次输入探针地址，用户名，密码，设置的检测多个id 如：\n" \
                 "**https://tz.example.com\nadmin\npassword\n1 2 3**\n" \
                 "（留空ID则显示所有服务器）\n取消点击 /cancel"
    elif config.tz_version == 'komari':
        prompt = "【设置 Komari 探针】\n\n请依次输入探针地址，API Key（可选），设置的检测节点 UUID 如：\n" \
                 "**https://komari.example.com\nxxxxxx（可留空）\nuuid1 uuid2**\n" \
                 "（留空API Key使用公开接口，留空UUID则显示所有节点）\n取消点击 /cancel"
    else:
        prompt = "【设置探针】\n\n请先选择探针类型\n取消点击 /cancel"
    
    send = await editMessage(call, prompt)
    if send is False:
        return

    txt = await callListen(call, 120, back_set_ikb('set_tz'))
    if txt is False:
        return

    elif txt.text == '/cancel':
        await txt.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_set_ikb('set_tz'))
    else:
        await txt.delete()
        try:
            c = txt.text.split("\n")
            s_tz = c[0].strip()
            
            if config.tz_version == 'v0':
                s_tzapi = c[1].strip()
                s_tzid = c[2].split() if len(c) > 2 else []
                
                config.tz_ad = s_tz
                config.tz_api = s_tzapi
                config.tz_id = s_tzid
                save_config()
                await editMessage(call,
                                  f"【Nezha V0 探针设置完成】\n\n【网址】\n{s_tz}\n\n【api_token】\n{s_tzapi}\n\n【检测的ids】\n{config.tz_id}",
                                  buttons=back_config_p_ikb)
            elif config.tz_version == 'v1':
                s_username = c[1].strip()
                s_password = c[2].strip()
                s_tzid = c[3].split() if len(c) > 3 else []
                
                config.tz_ad = s_tz
                config.tz_username = s_username
                config.tz_password = s_password
                config.tz_id = s_tzid
                save_config()
                await editMessage(call,
                                  f"【Nezha V1 探针设置完成】\n\n【网址】\n{s_tz}\n\n【用户名】\n{s_username}\n\n【检测的ids】\n{config.tz_id}",
                                  buttons=back_config_p_ikb)
            elif config.tz_version == 'komari':
                s_tzapi = c[1].strip() if len(c) > 1 else ''
                s_tzid = c[2].split() if len(c) > 2 else []
                
                config.tz_ad = s_tz
                config.tz_api = s_tzapi
                config.tz_id = s_tzid
                save_config()
                api_display = s_tzapi if s_tzapi else '未设置 (使用公开接口)'
                await editMessage(call,
                                  f"【Komari 探针设置完成】\n\n【网址】\n{s_tz}\n\n【API Key】\n{api_display}\n\n【检测的节点】\n{config.tz_id if config.tz_id else '全部节点'}",
                                  buttons=back_config_p_ikb)
            
            LOGGER.info(f"【admin】：{call.from_user.id} - 更新探针设置完成")
        except IndexError:
            await editMessage(call, f"请注意格式！您的输入如下：\n\n`{txt.text}`", buttons=back_set_ikb('set_tz'))



# 设置 emby 线路
@bot.on_callback_query(filters.regex('^set_line$') & admins_on_filter)
async def set_emby_line(_, call):
    await callAnswer(call, '设置emby线路')
    send = await editMessage(call,
                             "【设置线路】\n\n请发送向emby用户展示的emby地址\n取消点击 /cancel")
    if send is False:
        return

    txt = await callListen(call, 120, buttons=back_set_ikb('set_line'))
    if txt is False:
        return

    elif txt.text == '/cancel':
        await txt.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_set_ikb('set_line'))
    else:
        await txt.delete()
        config.emby_line = txt.text
        # 多服展示取 servers[].line，此处同步主服，保证面板设置立即生效
        config.servers[0].line = txt.text
        save_config()
        await editMessage(call, f"**【网址样式】:** \n\n{config.emby_line}\n\n设置完成！",
                          buttons=back_config_p_ikb)
        LOGGER.info(f"【admin】：{call.from_user.id} - 更新emby线路为{config.emby_line}设置完成")

@bot.on_callback_query(filters.regex('^set_whitelist_line$') & admins_on_filter)
async def set_whitelist_emby_line(_, call):
    await callAnswer(call, '设置白名单线路')
    send = await editMessage(call,
                             "【设置白名单线路】\n\n请发送白名单用户专属的emby地址\n取消点击 /cancel")
    if send is False:
        return

    txt = await callListen(call, 120, buttons=back_set_ikb('set_whitelist_line'))
    if txt is False:
        return

    elif txt.text == '/cancel':
        await txt.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_set_ikb('set_whitelist_line'))
    else:
        await txt.delete()
        config.emby_whitelist_line = txt.text
        save_config()
        await editMessage(call, f"**【白名单线路】:** \n\n{config.emby_whitelist_line}\n\n设置完成！",
                          buttons=back_config_p_ikb)
        LOGGER.info(f"【admin】：{call.from_user.id} - 更新白名单线路为{config.emby_whitelist_line}设置完成")


@bot.on_callback_query(filters.regex('set_update') & admins_on_filter)
async def set_auto_update(_, call):
    try:
        # 简化逻辑，只设置一次
        auto_update.status = not auto_update.status
        if auto_update.status:
            message = '您已开启 auto_update自动更新bot代码\n\n运行时间：12:30UTC+0800'
            LOGGER.info(f"【admin】：管理员 {call.from_user.first_name} 已启用 auto_update自动更新bot代码")
        else:
            message = '您已关闭 auto_update自动更新bot代码，如您需要更换仓库，请于配置文件中git_repo填写'
            LOGGER.info(f"【admin】：管理员 {call.from_user.first_name} 已关闭 auto_update自动更新bot代码")

        await callAnswer(call, message, True)
        await config_p_re(_, call)
        save_config()
    except Exception as e:
        # 异常处理，记录错误信息
        LOGGER.error(f"【admin】：管理员 {call.from_user.first_name} 尝试更改 auto_update状态时出错: {e}")


@bot.on_callback_query(filters.regex('^set_mp$') & admins_on_filter)
async def mp_config_panel(_, call):
    """MoviePilot 设置面板"""
    await callAnswer(call, 'MoviePilot 设置')
    lv_text = '无'
    if moviepilot.lv == 'a':
        lv_text = '白名单'
    elif moviepilot.lv == 'b':
        lv_text = '普通用户'
    await editMessage(call, 
                     "MoviePilot 设置面板\n\n"
                     f"当前状态：{'已开启' if moviepilot.status else '已关闭'}\n"
                     f"用户权限：{lv_text}可使用\n"
                     f"日志频道：{moviepilot.download_log_chatid or '未设置'}",
                     buttons=mp_config_ikb())

@bot.on_callback_query(filters.regex('^set_mp_status$') & admins_on_filter)
async def set_mp_status(_, call):
    """设置点播功能开关"""
    try:
        moviepilot.status = not moviepilot.status
        if moviepilot.status:
            message = '您已开启 MoviePilot 点播功能'
            scheduler.add_job(sync_download_tasks, 'interval', seconds=60, id='sync_download_tasks')
        else:
            message = '您已关闭 MoviePilot 点播功能'
            scheduler.remove_job(job_id='sync_download_tasks')
        
        await callAnswer(call, message, True)
        save_config()
        await mp_config_panel(_, call)
    except Exception as e:
        LOGGER.error(f"设置点播状态时出错: {str(e)}")

@bot.on_callback_query(filters.regex('set_mp_lv') & admins_on_filter)
async def set_mp_lv(_, call):
    """设置用户权限"""
    moviepilot.lv = 'a' if moviepilot.lv == 'b' else 'b'
    message = '已设置为仅白名单用户可用' if moviepilot.lv == 'a' else '已设置为普通用户可用'
    await callAnswer(call, message, True)
    save_config()
    await mp_config_panel(_, call)

@bot.on_callback_query(filters.regex('set_mp_log_channel') & admins_on_filter)
async def set_mp_log_channel(_, call):
    """设置日志频道"""
    await callAnswer(call, '设置日志频道')
    await editMessage(call,
                     f"设置日志频道\n\n"
                     f"当前频道：{moviepilot.download_log_chatid or '未设置'}\n"
                     f"请输入频道 ID\n"
                     f"取消请点 /cancel")
    
    txt = await callListen(call, 120)
    if txt is False or txt.text == '/cancel':
        return await mp_config_panel(_, call)
    
    try:
        chat_id = int(txt.text)
        moviepilot.download_log_chatid = chat_id
        save_config()
        await editMessage(call, f"日志频道已设置为 {chat_id}")
        await mp_config_panel(_, call)
    except ValueError:
        await editMessage(call, "请输入有效的频道 ID")
        await mp_config_panel(_, call)


@bot.on_callback_query(filters.regex('leave_ban') & admins_on_filter)
async def open_leave_ban(_, call):
    # 切换状态
    _open.leave_ban = not _open.leave_ban
    # 根据当前状态发送消息
    if _open.leave_ban:
        message = '**您已开启 退群封禁，用户退群后将被禁止入群**'
        log_message = "【admin】：管理员 {} 已调整 退群封禁设置为 True".format(call.from_user.first_name)
    else:
        message = '**您已关闭 退群封禁，用户退群后不会被禁止入群**'
        log_message = "【admin】：管理员 {} 已调整 退群封禁设置为 False".format(call.from_user.first_name)

    await callAnswer(call, message, True)
    await config_p_re(_, call)
    save_config()
    LOGGER.info(log_message)



@bot.on_callback_query(filters.regex('set_fuxx_pitao') & admins_on_filter)
async def set_fuxx_pitao(_, call):
    config.fuxx_pitao = not config.fuxx_pitao
    if not config.fuxx_pitao:
        message = '您已关闭 频道过滤功能，非白名单频道的消息不会被处理'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已调整 频道过滤功能 False"
    else:
        message = '您已开启 频道过滤功能，非白名单频道的消息将会被拦截'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已调整 频道过滤功能 True"

    await callAnswer(call, message, True)
    await config_p_re(_, call)
    save_config()
    LOGGER.info(log_message)
@bot.on_callback_query(filters.regex('set_activity_check_days') & admins_on_filter)
async def set_activity_check_days(_, call):
    await callAnswer(call, '设置活跃检测天数')
    send = await editMessage(call,
                             f"【设置活跃检测天数】\n\n请输入一个数字（天数）\n取消点击 /cancel\n\n当前活跃检测天数: {config.activity_check_days}")
    if send is False:
        return
    txt = await callListen(call, 120, back_set_ikb('set_activity_check_days'))
    if txt is False:
        return

    elif txt.text == '/cancel':
        await txt.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_set_ikb('set_activity_check_days'))
    else:
        await txt.delete()
        try:
            days = int(txt.text)
            if days <= 0:
                raise ValueError("天数必须大于0")
        except ValueError:
            await editMessage(call, f"请注意格式! 请输入大于0的数字。您的输入如下: \n\n`{txt.text}`",
                              buttons=back_set_ikb('set_activity_check_days'))
        else:
            config.activity_check_days = days
            save_config()
            await editMessage(call,
                              f"【活跃检测天数】\n\n{days}天，设置完成",
                              buttons=back_config_p_ikb)
            LOGGER.info(f"【admin】：{call.from_user.id} - 更新活跃检测天数为{days}天完成")
@bot.on_callback_query(filters.regex('^set_freeze_days$') & admins_on_filter)
async def set_freeze_days(_, call):
    await callAnswer(call, '设置封存账号天数')
    await editMessage(call, f'【设置封存账号天数】\n\n请输入一个大于 0 的数字\n取消点击 /cancel\n\n当前：{config.freeze_days} 天')
    txt = await callListen(call, 120, back_set_ikb('set_freeze_days'))
    if txt is False:
        return
    if txt.text == '/cancel':
        await txt.delete()
        return await editMessage(call, '已取消设置', buttons=back_set_ikb('set_freeze_days'))
    await txt.delete()
    try:
        days = int(txt.text)
        if days <= 0:
            raise ValueError
    except ValueError:
        return await editMessage(call, '请输入大于 0 的整数', buttons=back_set_ikb('set_freeze_days'))
    config.freeze_days = days
    save_config()
    await editMessage(call, f'封存账号天数已设置为 {days} 天', buttons=back_config_p_ikb)


@bot.on_callback_query(filters.regex('^set_client_filter$') & admins_on_filter)
async def set_client_filter_panel(_, call):
    """进入客户端过滤设置子面板"""
    await callAnswer(call, '客户端过滤')
    status = '已开启' if config.client_filter_enabled else '已关闭'
    mode = '黑名单模式' if config.client_filter_mode == 'blacklist' else '白名单模式'
    text = (
        f"**客户端过滤设置**\n\n"
        f"当前状态: **{status}**\n"
        f"过滤模式: **{mode}**\n\n"
        f"• 黑名单模式: 匹配拦截列表的客户端将被拦截\n"
        f"• 白名单模式: 未匹配允许列表的客户端将被拦截"
    )
    await editMessage(call, text, buttons=client_filter_panel())


@bot.on_callback_query(filters.regex('^toggle_client_filter$') & admins_on_filter)
async def toggle_client_filter(_, call):
    """切换客户端过滤开关"""
    config.client_filter_enabled = not config.client_filter_enabled
    if config.client_filter_enabled:
        message = '您已开启 客户端过滤功能'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已开启 客户端过滤功能"
    else:
        message = '您已关闭 客户端过滤功能'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已关闭 客户端过滤功能"
    await callAnswer(call, message, True)
    save_config()
    await set_client_filter_panel(_, call)
    LOGGER.info(log_message)


@bot.on_callback_query(filters.regex('^set_client_filter_mode$') & admins_on_filter)
async def set_client_filter_mode(_, call):
    """切换客户端过滤模式"""
    print(f"当前过滤模式: {config.client_filter_mode}")
    if config.client_filter_mode == 'blacklist':
        config.client_filter_mode = 'whitelist'
        message = '已切换到 白名单模式'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已切换客户端过滤模式为 白名单"
    else:
        config.client_filter_mode = 'blacklist'
        message = '已切换到 黑名单模式'
        log_message = f"【admin】：管理员 {call.from_user.first_name} 已切换客户端过滤模式为 黑名单"
    await callAnswer(call, message, True)
    save_config()
    await set_client_filter_panel(_, call)
    LOGGER.info(log_message)
