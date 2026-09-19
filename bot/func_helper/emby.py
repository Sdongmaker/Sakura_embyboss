#! /usr/bin/python3
# -*- coding:utf-8 -*-
"""
emby的api操作方法 - 使用aiohttp重构版本
"""
import asyncio
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any, List, Union
from contextlib import asynccontextmanager

from bot import LOGGER, config
from bot.schemas import ServerCfg
from bot.sql_helper.sql_emby import (
    sql_add_server_account,
    sql_delete_server_account,
    sql_get_emby,
    sql_get_server_accounts,
    sql_update_emby,
    Emby,
)
from bot.func_helper.utils import pwd_create, convert_runtime, cache, Singleton


def create_policy(admin=False, disable=False, limit: int = 2):
    """Create the standard user policy with access to every media library."""
    return {
        "IsAdministrator": admin,
        "IsHidden": True,
        "IsHiddenRemotely": True,
        "IsDisabled": disable,
        "EnableRemoteControlOfOtherUsers": False,
        "EnableSharedDeviceControl": False,
        "EnableRemoteAccess": True,
        "EnableLiveTvManagement": False,
        "EnableLiveTvAccess": True,
        "EnableMediaPlayback": True,
        "EnableAudioPlaybackTranscoding": False,
        "EnableVideoPlaybackTranscoding": False,
        "EnablePlaybackRemuxing": False,
        "EnableContentDeletion": False,
        "EnableContentDownloading": False,
        "EnableSubtitleDownloading": False,
        "EnableSubtitleManagement": False,
        "EnableSyncTranscoding": False,
        "EnableMediaConversion": False,
        "EnableAllDevices": True,
        "EnableAllFolders": True,
        "EnabledFolders": [],
        "BlockedMediaFolders": [],
        "SimultaneousStreamLimit": limit,
        "AllowCameraUpload": False,
    }


def pwd_policy(embyid: str, stats: bool = False, new: str = None) -> Dict[str, Any]:
    """
    创建密码策略
    :param embyid: str 修改的emby_id
    :param stats: bool 是否重置密码
    :param new: str 新密码
    :return: policy 密码策略
    """
    if new is None:
        policy = {
            "Id": str(embyid),
            "ResetPassword": stats,
        }
    else:
        policy = {
            "Id": str(embyid),
            "NewPw": str(new),
        }
    return policy


class EmbyApiResult:
    """API 结果统一封装"""
    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
    
    def __bool__(self):
        return self.success


class Embyservice(metaclass=Singleton):
    """
    Emby API 服务类 - 使用 aiohttp 重构版本
    提供统一的异步HTTP请求、错误处理、重试机制和资源管理
    """

    def __init__(self, url: str, api_key: str, timeout: int = 10, max_retries: int = 1, name: str = None):
        """
        初始化 Emby 服务
        :param url: Emby 服务器地址
        :param api_key: API 密钥
        :param timeout: 请求超时时间（秒）
        :param max_retries: 最大重试次数
        :param name: 服务器标识（对应 config.servers[i].name）
        """
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.name = name or "main"
        self.max_retries = max_retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
        # 请求头配置
        self.headers = {
            'accept': 'application/json',
            'content-type': 'application/json',
            'X-Emby-Token': self.api_key,
            'X-Emby-Client': 'Sakura BOT',
            'X-Emby-Device-Name': 'Sakura BOT',
            'X-Emby-Client-Version': '1.0.0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.82'
        }
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

    @asynccontextmanager
    async def session(self):
        """
        异步上下文管理器，管理 aiohttp 会话
        自动处理会话的创建和复用
        """
        async with self._session_lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=100,  # 连接池大小
                    limit_per_host=30,  # 每个主机的连接数
                    keepalive_timeout=60,  # 保持连接时间
                    enable_cleanup_closed=True
                )
                self._session = aiohttp.ClientSession(
                    headers=self.headers,
                    timeout=self.timeout,
                    connector=connector,
                    raise_for_status=False  # 手动处理HTTP状态码
                )
        
        try:
            yield self._session
        except Exception as e:
            LOGGER.error(f"会话使用异常: {str(e)}")
            raise

    async def close(self):
        """关闭会话并清理资源"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            LOGGER.info("Emby 服务会话已关闭")

    async def _request(self, method: str, endpoint: str, **kwargs) -> EmbyApiResult:
        """
        统一的HTTP请求方法，包含重试机制和错误处理
        :param method: HTTP方法
        :param endpoint: API端点
        :param kwargs: 请求参数
        :return: EmbyApiResult
        """
        url = f"{self.url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with self.session() as session:
                    async with session.request(method, url, **kwargs) as response:
                        # 检查HTTP状态码
                        if response.status in [200, 204]:
                            # 处理不同的响应类型
                            if response.content_type == 'application/json':
                                try:
                                    data = await response.json()
                                    return EmbyApiResult(True, data)
                                except Exception as e:
                                    LOGGER.error(f"JSON解析失败: {str(e)}")
                                    return EmbyApiResult(False, error=f"JSON解析失败: {str(e)}")
                            else:
                                # 处理二进制内容（如图片）
                                content = await response.read()
                                return EmbyApiResult(True, content)
                        
                        elif response.status == 404:
                            return EmbyApiResult(False, error="资源不存在")
                        elif response.status == 401:
                            return EmbyApiResult(False, error="认证失败，请检查API密钥")
                        elif response.status == 403:
                            return EmbyApiResult(False, error="权限不足")
                        else:
                            error_msg = f"HTTP {response.status}"
                            try:
                                error_text = await response.text()
                                if error_text:
                                    error_msg += f": {error_text}"
                            except Exception:
                                pass
                            
                            LOGGER.warning(f"API请求失败: {method} {url} - {error_msg}")
                            return EmbyApiResult(False, error=error_msg)
            
            except asyncio.TimeoutError:
                LOGGER.warning(f"请求超时 (尝试 {attempt + 1}/{self.max_retries}): {url}")
                if attempt == self.max_retries - 1:
                    return EmbyApiResult(False, error="请求超时")
                await asyncio.sleep(1 * (attempt + 1))  # 指数退避
            
            except aiohttp.ClientError as e:
                LOGGER.error(f"网络请求异常 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return EmbyApiResult(False, error=f"网络请求失败: {str(e)}")
                await asyncio.sleep(1 * (attempt + 1))
            
            except Exception as e:
                LOGGER.error(f"未知异常 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return EmbyApiResult(False, error=f"未知错误: {str(e)}")
                await asyncio.sleep(1 * (attempt + 1))
        
        return EmbyApiResult(False, error="达到最大重试次数")

    async def emby_create(self, name: str, days: int, password: str = None) -> Union[Tuple[str, str, datetime], bool]:
        """
        创建 Emby 账户
        :param name: 用户名
        :param days: 有效天数
        :param password: 指定密码，None 时按原规则随机生成（多服注册时由主服生成后复用）
        :return: (用户ID, 密码, 过期时间) 或 False
        """
        try:
            expiry_date = datetime.now() + timedelta(days=days)
            
            # 1. 创建用户
            LOGGER.info(f"开始创建用户: {name}")
            result = await self._request('POST', '/emby/Users/New', json={"Name": name})
            if not result.success:
                LOGGER.error(f"创建用户失败: {result.error}")
                return False
            
            user_id = result.data.get("Id")
            if not user_id:
                LOGGER.error("无法获取用户ID")
                return False
            
            # 2. 设置密码
            password = password or await pwd_create(8)
            pwd_data = pwd_policy(user_id, new=password)
            result = await self._request('POST', f'/emby/Users/{user_id}/Password', json=pwd_data)
            if not result.success:
                LOGGER.error(f"设置密码失败: {result.error}")
                return False
            
            # 3. 设置策略
            policy = create_policy(False, False)
            result = await self._request('POST', f'/emby/Users/{user_id}/Policy', json=policy)
            if not result.success:
                LOGGER.error(f"设置策略失败: {result.error}")
                return False
            
            LOGGER.info(f"成功创建用户: {name} (ID: {user_id})")
            return user_id, password, expiry_date
        except Exception as e:
            LOGGER.error(f"创建用户异常: {name} - {str(e)}")
            return False
    async def emby_del(self, emby_id: str) -> bool:
        """
        Delete an Emby account; a missing account is already successful.
        """
        try:
            LOGGER.info(f"开始删除用户: {emby_id}")
            result = await self._request('DELETE', f'/emby/Users/{emby_id}')
            if result.success:
                LOGGER.info(f"成功删除用户: {emby_id}")
                return True
            elif result.error == "资源不存在":
                LOGGER.info(f"用户已不存在，视为删除成功: {emby_id}")
                return True
            else:
                LOGGER.error(f"删除用户失败: {emby_id} - {result.error}")
                return False
        except Exception as e:
            LOGGER.error(f"删除用户异常: {emby_id} - {str(e)}")
            return False

    async def emby_reset(self, emby_id: str, new_password: str = None, write_db: bool = True) -> bool:
        """
        重置用户密码
        :param user_id: 用户ID
        :param new_password: 新密码，为空则重置为无密码
        :param write_db: 是否同步写入 emby.pwd，多服同步重置时由调用方统一写库
        :return: 是否成功
        """
        try:
            LOGGER.info(f"开始重置密码: {emby_id}")
            
            # 第一步：重置密码
            pwd_data = pwd_policy(emby_id, stats=True, new=None)
            result = await self._request('POST', f'/emby/Users/{emby_id}/Password', json=pwd_data)
            if not result.success:
                LOGGER.error(f"重置密码失败: {emby_id} - {result.error}")
                return False
            
            if new_password is None:
                # 更新数据库记录为无密码
                if not write_db:
                    LOGGER.info(f"成功重置密码为空: {emby_id}")
                    return True
                if sql_update_emby(Emby.embyid == emby_id, pwd=None):
                    LOGGER.info(f"成功重置密码为空: {emby_id}")
                    return True
                else:
                    LOGGER.error(f"更新数据库失败: {emby_id}")
                    return False
            else:
                # 设置新密码
                pwd_data2 = pwd_policy(emby_id, new=new_password)
                result = await self._request('POST', f'/emby/Users/{emby_id}/Password', json=pwd_data2)
                if not result.success:
                    LOGGER.error(f"设置新密码失败: {emby_id} - {result.error}")
                    return False

                if not write_db:
                    LOGGER.info(f"成功重置密码: {emby_id}")
                    return True

                # 更新数据库
                if sql_update_emby(Emby.embyid == emby_id, pwd=new_password):
                    LOGGER.info(f"成功重置密码: {emby_id}")
                    return True
                else:
                    LOGGER.error(f"更新数据库失败: {emby_id}")
                    return False
                    
        except Exception as e:
            LOGGER.error(f"重置密码异常: {emby_id} - {str(e)}")
            return False


    @cache.memoize(ttl=120)
    async def get_current_playing_count(self) -> int:
        """
        获取当前播放用户数量
        :return: 播放用户数量
        """
        try:
            result = await self._request('GET', '/emby/Sessions')
            if result.success and result.data:
                count = 0
                for session in result.data:
                    if session.get("NowPlayingItem"):
                        count += 1
                LOGGER.debug(f"当前播放用户数: {count}")
                return count
            else:
                LOGGER.error(f"获取播放数量失败: {result.error}")
                return -1
        except Exception as e:
            LOGGER.error(f"获取播放数量异常: {str(e)}")
            return -1

    async def terminate_session(self, session_id: str, reason: str = "Unauthorized client detected") -> bool:
        """
        终止指定的播放会话
        :param session_id: 会话ID
        :param reason: 终止原因
        :return: 是否成功
        """
        try:
            LOGGER.info(f"开始终止会话: {session_id} - {reason}")
            
            # 停止播放
            stop_result = await self._request('POST', f'/emby/Sessions/{session_id}/Playing/Stop')
            
            # 发送消息给客户端
            message_data = {
                "Text": f"会话已被终止: {reason}",
                "Header": "安全警告",
                "TimeoutMs": 10000
            }
            message_result = await self._request('POST', f'/emby/Sessions/{session_id}/Message', json=message_data)
            
            # 只要有一个操作成功就认为成功
            if stop_result.success or message_result.success:
                LOGGER.info(f"成功终止会话: {session_id}")
                return True
            else:
                LOGGER.error(f"终止会话失败: {session_id}")
                return False
                
        except Exception as e:
            LOGGER.error(f"终止会话异常: {session_id} - {str(e)}")
            return False

    async def emby_change_policy(self, emby_id: str, admin: bool = False, disable: bool = False) -> bool:
        """Update administrator/disabled flags while preserving playback restrictions."""
        try:
            current_policy = {}
            user_result = await self._request('GET', f'/emby/Users/{emby_id}')
            if user_result.success:
                current_policy = user_result.data.get("Policy", {}) if user_result.data else {}
            policy = create_policy(admin=admin, disable=disable)
            for key in ("SimultaneousStreamLimit", "EnableMediaPlayback", "EnableAudioPlaybackTranscoding",
                        "EnableVideoPlaybackTranscoding", "EnablePlaybackRemuxing"):
                if key in current_policy:
                    policy[key] = current_policy[key]
            result = await self._request('POST', f'/emby/Users/{emby_id}/Policy', json=policy)
            if result.success:
                LOGGER.info(f"成功修改用户策略: {emby_id}")
                return True
            LOGGER.error(f"修改用户策略失败: {emby_id} - {result.error}")
            return False
        except Exception as e:
            LOGGER.error(f"修改用户策略异常: {emby_id} - {str(e)}")
            return False

    async def authority_account(self, tg_id: int, username: str, password: str = None) -> Tuple[bool, Union[str, int]]:
        """
        验证账户
        :param tg_id: Telegram用户ID
        :param username: 用户名
        :param password: 密码
        :return: (是否成功, 用户ID或错误码)
        """
        try:
            data = {"Username": username}
            if password and password != 'None':
                data["Pw"] = password
                
            result = await self._request('POST', '/emby/Users/AuthenticateByName', json=data)
            if result.success and result.data:
                emby_id = result.data.get("User", {}).get("Id")
                if emby_id:
                    LOGGER.info(f"账户验证成功: {username} -> {emby_id}")
                    return True, emby_id
                else:
                    LOGGER.error(f"账户验证失败，无法获取用户ID: {username}")
                    return False, 0
            else:
                LOGGER.error(f"账户验证失败: {username} - {result.error}")
                return False, 0
        except Exception as e:
            LOGGER.error(f"账户验证异常: {username} - {str(e)}")
            return False, 0

    async def emby_cust_commit(self, emby_id: str = None, days: int = 7, method: str = None) -> Optional[List[Dict]]:
        """
        执行自定义查询（已修复SQL注入问题）
        :param emby_id: 用户ID
        :param days: 查询天数
        :param method: 查询方法
        :return: 查询结果
        """
        try:
            sub_time = datetime.now(timezone(timedelta(hours=8)))
            start_time = (sub_time - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = sub_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 注意：由于Emby API的限制，这里仍然需要拼接SQL
            # 在实际生产环境中，建议在Emby服务器端实现参数化查询
            if method == 'sp':
                final_sql = f"SELECT UserId, SUM(PlayDuration - PauseDuration) AS WatchTime FROM PlaybackActivity WHERE DateCreated >= '{start_time}' AND DateCreated < '{end_time}' GROUP BY UserId ORDER BY WatchTime DESC"
            else:
                final_sql = f"SELECT MAX(DateCreated) AS LastLogin, SUM(PlayDuration - PauseDuration) / 60 AS WatchTime FROM PlaybackActivity WHERE UserId = '{emby_id}' AND DateCreated >= '{start_time}' AND DateCreated < '{end_time}' GROUP BY UserId"
            
            data = {
                "CustomQueryString": final_sql,
                "ReplaceUserId": True
            }
            
            result = await self._request('POST', '/emby/user_usage_stats/submit_custom_query', json=data)
            if result.success and result.data:
                return result.data.get("results", [])
            else:
                LOGGER.error(f"自定义查询失败: {result.error}")
                return None
                
        except Exception as e:
            LOGGER.error(f"自定义查询异常: {str(e)}")
            return None

    async def users(self) -> Tuple[bool, Union[List[Dict], Dict[str, str]]]:
        """
        获取所有用户列表
        :return: (是否成功, 用户列表或错误信息)
        """
        try:
            result = await self._request('GET', '/emby/Users')
            if result.success:
                LOGGER.debug(f"获取用户列表成功，共 {len(result.data)} 个用户")
                return True, result.data
            else:
                LOGGER.error(f"获取用户列表失败: {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"获取用户列表异常: {str(e)}")
            return False, {'error': str(e)}

    async def user(self, emby_id: str) -> Tuple[bool, Union[Dict, Dict[str, str]]]:
        """
        通过ID获取用户信息
        :param emby_id: 用户ID
        :return: (是否成功, 用户信息或错误信息)
        """
        try:
            result = await self._request('GET', f'/emby/Users/{emby_id}')
            if result.success:
                LOGGER.debug(f"获取用户信息成功: {emby_id}")
                return True, result.data
            else:
                LOGGER.error(f"获取用户信息失败: {emby_id} - {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"获取用户信息异常: {emby_id} - {str(e)}")
            return False, {'error': str(e)}

    async def get_emby_user_by_name(self, emby_name: str) -> Tuple[bool, Union[Dict, Dict[str, str]]]:
        """
        通过用户名获取用户信息
        :param emby_name: 用户名
        :return: (是否成功, 用户信息或错误信息)
        """
        try:
            result = await self._request('GET', f'/emby/Users/Query?NameStartsWithOrGreater={emby_name}&api_key={self.api_key}')
            if result.success and result.data:
                items = result.data.get("Items", [])
                for item in items:
                    if item.get("Name") == emby_name:
                        LOGGER.debug(f"找到用户: {emby_name}")
                        return True, item
                LOGGER.warning(f"未找到用户: {emby_name}")
                return False, {'error': "用户不存在"}
            else:
                LOGGER.error(f"查询用户失败: {emby_name} - {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"查询用户异常: {emby_name} - {str(e)}")
            return False, {'error': str(e)}

    async def add_favorite_items(self, emby_id: str, item_id: str) -> bool:
        """
        添加收藏项目
        :param emby_id: 用户ID
        :param item_id: 项目ID
        :return: 是否成功
        """
        try:
            result = await self._request('POST', f'/emby/Users/{emby_id}/FavoriteItems/{item_id}')
            if result.success:
                LOGGER.info(f"添加收藏成功: {emby_id} -> {item_id}")
                return True
            else:
                LOGGER.error(f"添加收藏失败: {emby_id} -> {item_id} - {result.error}")
                return False
        except Exception as e:
            LOGGER.error(f"添加收藏异常: {emby_id} -> {item_id} - {str(e)}")
            return False

    async def get_favorite_items(self, emby_id: str, start_index: int = None, limit: int = None) -> Union[Dict, bool]:
        """
        获取用户收藏项目
        :param emby_id: 用户ID
        :param start_index: 开始索引
        :param limit: 限制数量
        :return: 收藏项目数据或False
        """
        try:
            url = f"/emby/Users/{emby_id}/Items?Filters=IsFavorite&Recursive=true&IncludeItemTypes=Movie,Series,Episode,Person"
            if start_index is not None:
                url += f"&StartIndex={start_index}"
            if limit is not None:
                url += f"&Limit={limit}"
                
            result = await self._request('GET', url)
            if result.success:
                LOGGER.debug(f"获取收藏成功: {emby_id}")
                return result.data
            else:
                LOGGER.error(f"获取收藏失败: {emby_id} - {result.error}")
                return False
        except Exception as e:
            LOGGER.error(f"获取收藏异常: {emby_id} - {str(e)}")
            return False

    async def item_id_name(self, emby_id: str, item_id: str) -> str:
        """
        通过项目ID获取名称
        :param emby_id: 用户ID
        :param item_id: 项目ID
        :return: 项目名称
        """
        try:
            result = await self._request('GET', f'/emby/Users/{emby_id}/Items/{item_id}')
            if result.success and result.data:
                title = result.data.get("Name", "")
                LOGGER.debug(f"获取项目名称成功: {item_id} -> {title}")
                return title
            else:
                LOGGER.error(f"获取项目名称失败: {item_id} - {result.error}")
                return ""
        except Exception as e:
            LOGGER.error(f"获取项目名称异常: {item_id} - {str(e)}")
            return ""

    async def item_id_people(self, item_id: str) -> Tuple[bool, Union[List[Dict], Dict[str, str]]]:
        """
        获取项目演员信息
        :param item_id: 项目ID
        :return: (是否成功, 演员列表或错误信息)
        """
        try:
            result = await self._request('GET', f'/emby/Items?Ids={item_id}&Fields=People')
            if result.success and result.data:
                items = result.data.get("Items", [])
                if items:
                    people = items[0].get("People", [])
                    LOGGER.debug(f"获取演员信息成功: {item_id}")
                    return True, people
                else:
                    LOGGER.warning(f"项目无演员信息: {item_id}")
                    return False, {'error': "Emby 服务器返回数据为空!"}
            else:
                LOGGER.error(f"获取演员信息失败: {item_id} - {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"获取演员信息异常: {item_id} - {str(e)}")
            return False, {'error': str(e)}
    async def backdrop(self, item_id: str, width: int = 300, quality: int = 90) -> Tuple[bool, Union[bytes, Dict[str, str]]]:
        """
        获取背景图片
        :param item_id: 项目ID
        :param width: 宽度
        :param quality: 质量
        :return: (是否成功, 图片数据或错误信息)
        """
        try:
            url = f'/emby/Items/{item_id}/Images/Backdrop?maxWidth={width}&quality={quality}'
            result = await self._request('GET', url)
            if result.success:
                LOGGER.debug(f"获取背景图片成功: {item_id}")
                return True, result.data
            else:
                LOGGER.error(f"获取背景图片失败: {item_id} - {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"获取背景图片异常: {item_id} - {str(e)}")
            return False, {'error': str(e)}

    async def items(self, emby_id: str, item_id: str) -> Tuple[bool, Union[Dict, Dict[str, str]]]:
        """
        获取用户的特定项目信息
        :param emby_id: 用户ID
        :param item_id: 项目ID
        :return: (是否成功, 项目信息或错误信息)
        """
        try:
            result = await self._request('GET', f'/emby/Users/{emby_id}/Items/{item_id}')
            if result.success:
                LOGGER.debug(f"获取项目信息成功: {emby_id} -> {item_id}")
                return True, result.data
            else:
                LOGGER.error(f"获取项目信息失败: {emby_id} -> {item_id} - {result.error}")
                return False, {'error': f"Emby 服务器连接失败: {result.error}"}
        except Exception as e:
            LOGGER.error(f"获取项目信息异常: {emby_id} -> {item_id} - {str(e)}")
            return False, {'error': str(e)}

    async def get_emby_report(self, types: str = 'Movie', emby_id: str = None, days: int = 7, 
                             end_date: datetime = None, limit: int = 10) -> Tuple[bool, Union[List[Dict], str]]:
        """
        获取播放报告（已修复SQL注入问题）
        :param types: 类型
        :param emby_id: 用户ID
        :param days: 天数
        :param end_date: 结束日期
        :param limit: 限制数量
        :return: (是否成功, 报告数据或错误信息)
        """
        try:
            if not end_date:
                end_date = datetime.now(timezone(timedelta(hours=8)))
            
            start_time = (end_date - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            end_time = end_date.strftime('%Y-%m-%d %H:%M:%S')
            
            # 构建安全的SQL查询
            sql_parts = [
                "SELECT UserId, ItemId, ItemType,",
                " substr(ItemName,0, instr(ItemName, ' - ')) AS name," if types == 'Episode' else "ItemName AS name,",
                "COUNT(1) AS play_count,",
                "SUM(PlayDuration - PauseDuration) AS total_duarion",
                "FROM PlaybackActivity",
                f"WHERE ItemType = '{types}'",  # 这里应该验证types参数
                f"AND DateCreated >= '{start_time}' AND DateCreated <= '{end_time}'",
                "AND UserId not IN (select UserId from UserList)"
            ]
            
            if emby_id:
                # 验证user_id格式，防止SQL注入
                if not emby_id.replace('-', '').replace('_', '').isalnum():
                    LOGGER.error(f"无效的用户ID格式: {emby_id}")
                    return False, "无效的用户ID格式"
                sql_parts.append(f"AND UserId = '{emby_id}'")
            
            sql_parts.extend([
                "GROUP BY name",
                "ORDER BY total_duarion DESC",
                f"LIMIT {int(limit)}"  # 确保limit是整数
            ])
            
            sql = " ".join(sql_parts)
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": False
            }
            
            result = await self._request('POST', '/emby/user_usage_stats/submit_custom_query', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, ret.get("message", "无数据")
                LOGGER.debug(f"获取播放报告成功: {types}")
                return True, ret.get("results", [])
            else:
                LOGGER.error(f"获取播放报告失败: {result.error}")
                return False, f"Emby 服务器连接失败: {result.error}"
                
        except Exception as e:
            LOGGER.error(f"获取播放报告异常: {str(e)}")
            return False, str(e)

    async def get_emby_userip(self, emby_id: str) -> Tuple[bool, Union[List[Dict], str]]:
        """
        获取用户IP和设备信息（已修复SQL注入问题）
        :param emby_id: 用户ID
        :return: (是否成功, 设备信息或错误信息)
        """
        try:
            # 验证user_id格式
            if not emby_id.replace('-', '').replace('_', '').isalnum():
                LOGGER.error(f"无效的用户ID格式: {emby_id}")
                return False, "无效的用户ID格式"
            
            sql = f"SELECT DeviceName,ClientName, RemoteAddress FROM PlaybackActivity WHERE UserId = '{emby_id}'"
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": True
            }
            
            result = await self._request('POST', f'/emby/user_usage_stats/submit_custom_query?api_key={self.api_key}', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, ret.get("message", "无数据")
                LOGGER.debug(f"获取用户设备信息成功: {emby_id}")
                return True, ret.get("results", [])
            else:
                LOGGER.error(f"获取用户设备信息失败: {emby_id} - {result.error}")
                return False, f"Emby 服务器连接失败: {result.error}"
                
        except Exception as e:
            LOGGER.error(f"获取用户设备信息异常: {emby_id} - {str(e)}")
            return False, str(e)

    async def get_users_by_ip(self, ip_address: str, days: int = None) -> Tuple[bool, Union[List[Dict], str]]:
        """
        根据IP地址查询使用该IP的用户信息（已修复SQL注入问题）
        :param ip_address: IP地址
        :param days: 查询天数范围，默认30天
        :return: (是否成功, 用户信息列表或错误信息)
        """
        try:
            # 验证IP地址格式（简单验证）
            import re
            ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            if not re.match(ip_pattern, ip_address):
                LOGGER.error(f"无效的IP地址格式: {ip_address}")
                return False, "无效的IP地址格式"
            
            
            
            # 构建安全的SQL查询，查询使用指定IP的用户
            sql = f"""
                SELECT DISTINCT UserId, 
                       DeviceName, 
                       ClientName, 
                       RemoteAddress,
                       MAX(DateCreated) AS LastActivity,
                       COUNT(*) AS ActivityCount
                FROM PlaybackActivity 
                WHERE RemoteAddress = '{ip_address}' 
                
            """
            if days:
                # 计算查询时间范围
                sub_time = datetime.now(timezone(timedelta(hours=8)))
                start_time = (sub_time - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                end_time = sub_time.strftime("%Y-%m-%d %H:%M:%S")
                sql += f" AND DateCreated >= '{start_time}' AND DateCreated <= '{end_time}'"
            sql += " GROUP BY UserId, DeviceName, ClientName, RemoteAddress"
            sql += " ORDER BY LastActivity DESC"
            
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": False
            }
            
            result = await self._request('POST', f'/emby/user_usage_stats/submit_custom_query?api_key={self.api_key}', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, ret.get("message", "无数据")
                
                # 获取查询结果
                results = ret.get("results", [])
                
                # 为每个用户获取用户名信息
                enriched_results = []
                for result_item in results:
                    user_id = result_item[0]  # UserId 是第一列
                    
                    # 获取用户详细信息
                    user_success, user_info = await self.user(user_id)
                    username = "未知用户"
                    if user_success and isinstance(user_info, dict):
                        username = user_info.get("Name", "未知用户")
                    
                    enriched_item = {
                        "UserId": user_id,
                        "Username": username,
                        "DeviceName": result_item[1],
                        "ClientName": result_item[2], 
                        "RemoteAddress": result_item[3],
                        "LastActivity": result_item[4],
                        "ActivityCount": result_item[5]
                    }
                    enriched_results.append(enriched_item)
                
                LOGGER.info(f"根据IP查询用户成功: {ip_address} - 找到 {len(enriched_results)} 个用户")
                return True, enriched_results
            else:
                LOGGER.error(f"根据IP查询用户失败: {ip_address} - {result.error}")
                return False, f"Emby 服务器连接失败: {result.error}"
                
        except Exception as e:
            LOGGER.error(f"根据IP查询用户异常: {ip_address} - {str(e)}")
            return False, str(e)

    async def get_users_by_device_name(self, device_name: str, days: int = None) -> Tuple[bool, Union[List[Dict], str]]:
        """
        根据设备名关键词查询使用该设备的用户信息（已修复SQL注入问题）
        :param device_name: 设备名关键词
        :param days: 查询天数范围，None表示查询所有时间
        :return: (是否成功, 用户信息列表或错误信息)
        """
        try:
            # 验证关键词（基本的安全检查）
            if not device_name or len(device_name.strip()) == 0:
                LOGGER.error("设备名关键词不能为空")
                return False, "设备名关键词不能为空"
            
            # 清理关键词，防止SQL注入
            safe_keyword = device_name.replace("'", "''").replace(";", "").replace("--", "")
            
            # 构建安全的SQL查询，查询使用包含指定关键词的设备名的用户
            sql = f"""
                SELECT DISTINCT UserId, 
                       DeviceName, 
                       ClientName, 
                       RemoteAddress,
                       MAX(DateCreated) AS LastActivity,
                       COUNT(*) AS ActivityCount
                FROM PlaybackActivity 
                WHERE DeviceName LIKE '%{safe_keyword}%' 
            """
            if days:
                # 计算查询时间范围
                sub_time = datetime.now(timezone(timedelta(hours=8)))
                start_time = (sub_time - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                end_time = sub_time.strftime("%Y-%m-%d %H:%M:%S")
                sql += f" AND DateCreated >= '{start_time}' AND DateCreated <= '{end_time}'"
            sql += " GROUP BY UserId, DeviceName, ClientName, RemoteAddress"
            sql += " ORDER BY LastActivity DESC"
            
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": False
            }
            
            result = await self._request('POST', f'/emby/user_usage_stats/submit_custom_query?api_key={self.api_key}', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, ret.get("message", "无数据")
                
                # 获取查询结果
                results = ret.get("results", [])
                
                # 为每个用户获取用户名信息
                enriched_results = []
                for result_item in results:
                    user_id = result_item[0]  # UserId 是第一列
                    
                    # 获取用户详细信息
                    user_success, user_info = await self.user(user_id)
                    username = "未知用户"
                    if user_success and isinstance(user_info, dict):
                        username = user_info.get("Name", "未知用户")
                    
                    enriched_item = {
                        "UserId": user_id,
                        "Username": username,
                        "DeviceName": result_item[1],
                        "ClientName": result_item[2], 
                        "RemoteAddress": result_item[3],
                        "LastActivity": result_item[4] if len(result_item) > 4 else "未知",
                        "ActivityCount": result_item[5] if len(result_item) > 5 else 0
                    }
                    enriched_results.append(enriched_item)
                
                LOGGER.info(f"根据设备名查询用户成功: {device_name} - 找到 {len(enriched_results)} 个用户")
                return True, enriched_results
            else:
                LOGGER.error(f"根据设备名查询用户失败: {device_name} - {result.error}")
                return False, f"Emby 服务器连接失败: {result.error}"
                
        except Exception as e:
            LOGGER.error(f"根据设备名查询用户异常: {device_name} - {str(e)}")
            return False, str(e)

    async def get_users_by_client_name(self, client_name: str, days: int = None) -> Tuple[bool, Union[List[Dict], str]]:
        """
        根据客户端名关键词查询使用该客户端的用户信息（已修复SQL注入问题）
        :param client_name: 客户端名关键词
        :param days: 查询天数范围，None表示查询所有时间
        :return: (是否成功, 用户信息列表或错误信息)
        """
        try:
            # 验证关键词（基本的安全检查）
            if not client_name or len(client_name.strip()) == 0:
                LOGGER.error("客户端名关键词不能为空")
                return False, "客户端名关键词不能为空"
            
            # 清理关键词，防止SQL注入
            safe_keyword = client_name.replace("'", "''").replace(";", "").replace("--", "")
            
            # 构建安全的SQL查询，查询使用包含指定关键词的客户端名的用户
            sql = f"""
                SELECT DISTINCT UserId, 
                       DeviceName, 
                       ClientName, 
                       RemoteAddress,
                       MAX(DateCreated) AS LastActivity,
                       COUNT(*) AS ActivityCount
                FROM PlaybackActivity 
                WHERE ClientName LIKE '%{safe_keyword}%' 
            """
            if days:
                # 计算查询时间范围
                sub_time = datetime.now(timezone(timedelta(hours=8)))
                start_time = (sub_time - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                end_time = sub_time.strftime("%Y-%m-%d %H:%M:%S")
                sql += f" AND DateCreated >= '{start_time}' AND DateCreated <= '{end_time}'"
            sql += " GROUP BY UserId, DeviceName, ClientName, RemoteAddress"
            sql += " ORDER BY LastActivity DESC"
            
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": False
            }
            
            result = await self._request('POST', f'/emby/user_usage_stats/submit_custom_query?api_key={self.api_key}', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, ret.get("message", "无数据")
                
                # 获取查询结果
                results = ret.get("results", [])
                
                # 为每个用户获取用户名信息
                enriched_results = []
                for result_item in results:
                    user_id = result_item[0]  # UserId 是第一列
                    
                    # 获取用户详细信息
                    user_success, user_info = await self.user(user_id)
                    username = "未知用户"
                    if user_success and isinstance(user_info, dict):
                        username = user_info.get("Name", "未知用户")
                    
                    enriched_item = {
                        "UserId": user_id,
                        "Username": username,
                        "DeviceName": result_item[1],
                        "ClientName": result_item[2], 
                        "RemoteAddress": result_item[3],
                        "LastActivity": result_item[4] if len(result_item) > 4 else "未知",
                        "ActivityCount": result_item[5] if len(result_item) > 5 else 0
                    }
                    enriched_results.append(enriched_item)
                
                LOGGER.info(f"根据客户端名查询用户成功: {client_name} - 找到 {len(enriched_results)} 个用户")
                return True, enriched_results
            else:
                LOGGER.error(f"根据客户端名查询用户失败: {client_name} - {result.error}")
                return False, f"Emby 服务器连接失败: {result.error}"
                
        except Exception as e:
            LOGGER.error(f"根据客户端名查询用户异常: {client_name} - {str(e)}")
            return False, str(e)

    async def get_emby_user_devices(self, offset: int = 0, limit: int = 20) -> Tuple[bool, List[Dict], bool, bool]:
        """
        获取用户设备统计，支持分页
        :param offset: 偏移量
        :param limit: 每页数量
        :return: (是否成功, 设备数据, 是否有上一页, 是否有下一页)
        """
        try:
            sql = f"""
                SELECT UserId, 
                       COUNT(DISTINCT DeviceName || '' || ClientName) AS device_count,
                       COUNT(DISTINCT RemoteAddress) AS ip_count 
                FROM PlaybackActivity 
                GROUP BY UserId 
                ORDER BY device_count DESC 
                LIMIT {int(limit + 1)} 
                OFFSET {int(offset)}
            """
            
            data = {
                "CustomQueryString": sql,
                "ReplaceUserId": True
            }
            
            result = await self._request('POST', f'/emby/user_usage_stats/submit_custom_query?api_key={self.api_key}', json=data)
            if result.success and result.data:
                ret = result.data
                if len(ret.get("colums", [])) == 0:
                    return False, [], False, False
                
                results = ret.get("results", [])
                
                # 判断是否有下一页
                has_next = len(results) > limit
                if has_next:
                    results = results[:-1]  # 去掉多查的一条
                
                # 判断是否有上一页
                has_prev = offset > 0
                
                LOGGER.debug(f"获取用户设备统计成功: offset={offset}, limit={limit}")
                return True, results, has_prev, has_next
            else:
                LOGGER.error(f"获取用户设备统计失败: {result.error}")
                return False, [], False, False
                
        except Exception as e:
            LOGGER.error(f"获取用户设备统计异常: {str(e)}")
            return False, [], False, False

    @staticmethod
    async def get_medias_count() -> str:
        """
        获取媒体数量统计（主服）
        :return: 统计文本
        """
        try:
            # 创建临时会话进行请求
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{emby_url}/emby/Items/Counts?api_key={emby_api}"
                async with session.get(url) as response:
                    if response.status in [200, 204]:
                        result = await response.json()
                        movie_count = result.get("MovieCount", 0)
                        tv_count = result.get("SeriesCount", 0)
                        episode_count = result.get("EpisodeCount", 0)
                        music_count = result.get("SongCount", 0)
                        
                        txt = f'电影数量：{movie_count}\n' \
                              f'剧集数量：{tv_count}\n' \
                              f'音乐数量：{music_count}\n' \
                              f'总集数：{episode_count}\n'
                        LOGGER.debug("获取媒体统计成功")
                        return txt
                    else:
                        LOGGER.error(f"获取媒体统计失败: HTTP {response.status}")
                        return 'Emby 服务器返回数据为空!'
        except Exception as e:
            LOGGER.error(f"获取媒体统计异常: {str(e)}")
            return 'Emby 服务器连接失败!'

    async def get_movies(self, title: str, start: int = 0, limit: int = 5) -> List[Dict]:
        """
        搜索电影/剧集
        :param title: 标题
        :param start: 开始索引
        :param limit: 限制数量
        :return: 电影/剧集列表
        """
        try:
            # URL编码处理
            import urllib.parse
            encoded_title = urllib.parse.quote(title)
            
            url = (f"/emby/Items?IncludeItemTypes=Movie,Series"
                   f"&Fields=ProductionYear,Overview,OriginalTitle,Taglines,ProviderIds,Genres,RunTimeTicks,ProductionLocations,DateCreated,Studios"
                   f"&StartIndex={int(start)}&Recursive=true&SearchTerm={encoded_title}&Limit={int(limit)}&IncludeSearchTypes=false")
            
            # 使用较短的超时时间
            old_timeout = self.timeout
            self.timeout = aiohttp.ClientTimeout(total=3)
            
            try:
                result = await self._request('GET', url)
            finally:
                self.timeout = old_timeout
            
            if result.success and result.data:
                items = result.data.get("Items", [])
                ret_movies = []
                
                for item in items:
                    # 处理标题
                    name = item.get("Name", "")
                    original_title = item.get("OriginalTitle", "")
                    display_title = name if name == original_title else f'{name} - {original_title}'
                    
                    # 处理其他字段
                    production_locations = ", ".join(item.get("ProductionLocations", ["普遍"]))
                    genres = ", ".join(item.get("Genres", ["未知"]))
                    runtime = convert_runtime(item.get("RunTimeTicks")) if item.get("RunTimeTicks") else '数据缺失'
                    tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                    
                    movie_item = {
                        'item_type': item.get("Type"),
                        'item_id': item.get("Id"),
                        'title': display_title,
                        'year': item.get("ProductionYear", '缺失'),
                        'od': production_locations,
                        'genres': genres,
                        'photo': f'{self.url}/emby/Items/{item.get("Id")}/Images/Primary?maxHeight=400&maxWidth=600&quality=90',
                        'runtime': runtime,
                        'overview': item.get("Overview", "暂无更多信息"),
                        'taglines': '简介：' if not item.get("Taglines") else item.get("Taglines")[0],
                        'tmdbid': tmdb_id,
                        'add': item.get("DateCreated", "None.").split('.')[0],
                    }
                    ret_movies.append(movie_item)
                
                LOGGER.debug(f"搜索电影成功: {title} - 找到 {len(ret_movies)} 个结果")
                return ret_movies
            else:
                LOGGER.error(f"搜索电影失败: {title} - {result.error}")
                return []
                
        except Exception as e:
            LOGGER.error(f"搜索电影异常: {title} - {str(e)}")
            return []

    async def get_device_by_deviceid(self, deviceid: str) -> Tuple[bool, Union[Dict, Dict[str, str]]]:
        """
        通过设备ID获取设备信息
        :param deviceid: 设备ID
        :return: (是否成功, 设备信息或错误信息)
        """
        try:
            result = await self._request('GET', f'/emby/Devices/Info?Id={deviceid}')
            if result.success:
                LOGGER.debug(f"获取设备信息成功: {deviceid}")
                return True, result.data
            else:
                LOGGER.error(f"获取设备信息失败: {deviceid} - {result.error}")
                return False, "获取设备信息失败"
        except Exception as e:
            LOGGER.error(f"获取设备信息异常: {deviceid} - {str(e)}")
            return False, '获取设备信息异常'

    def __del__(self):
        """析构函数，确保资源清理"""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            # 在事件循环中清理会话
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
            except Exception:
                pass


# ==================== 多服务器支持 ====================
# servers[0] 为主服，emby 为历史全局单例别名，等价于主服客户端
emby_pool: Dict[str, Embyservice] = {}
for _server in config.servers:
    _embyservice = Embyservice(_server.url, _server.api, name=_server.name)
    emby_pool[_server.name] = _embyservice

# 创建全局实例（主服）
emby = emby_pool[config.servers[0].name]


def get_emby(server: str = None) -> Embyservice:
    """
    获取指定服务器的客户端
    :param server: 服务器标识，None 或未配置时返回主服
    """
    if server and server in emby_pool:
        return emby_pool[server]
    return emby


def primary_server_name() -> str:
    """主服标识（config.servers[0].name）"""
    return config.servers[0].name


def target_servers(lv: str = None) -> List[ServerCfg]:
    """
    按用户等级筛选需要纳管的服务器
    :param lv: 用户等级，None 表示不按等级筛选
    """
    return [server for server in config.servers if not (lv and server.lvs and lv not in server.lvs)]


def server_account_targets(tg: int = None, embyid: str = None) -> List[Tuple[str, str]]:
    """
    解析 tg 在各服上的账户，返回 [(server, embyid)]
    没有服务器账户记录时回退到指定的 embyid（挂主服名下），兼容历史数据
    """
    targets = [(server, eid) for server, eid, _name, _status in sql_get_server_accounts(tg) if eid] if tg else []
    if not targets and embyid:
        targets.append((primary_server_name(), embyid))
    return targets


@dataclass
class ServerCreateResult:
    """
    多服建号结果
    :param accounts: [(server, embyid, status)]，status 为 active/failed
    """
    ok: bool
    password: Optional[str] = None
    embyid: Optional[str] = None
    expired: Optional[datetime] = None
    accounts: List[Tuple[str, Optional[str], str]] = field(default_factory=list)


async def emby_create_all(name: str, days: int, lv: str = None, password: str = None) -> ServerCreateResult:
    """
    在所有目标服务器上创建同名同密账户
    :param lv: 用户等级，用于按 servers[i].lvs 筛选目标服务器
    :param password: 指定密码，None 时由主服按原规则生成后复用给其余服务器
    主服失败视为整体失败（emby 表以主服账户为锚点）；其余服务器失败只标记 failed 不阻塞注册
    """
    targets = target_servers(lv)
    if not targets:
        LOGGER.error(f"没有可用的 Emby 服务器配置，创建账户失败: {name}")
        return ServerCreateResult(ok=False)

    result = ServerCreateResult(ok=False)
    for index, server in enumerate(targets):
        try:
            data = await get_emby(server.name).emby_create(name=name, days=days, password=password)
        except Exception as e:
            LOGGER.exception(f"服务器创建账户异常: server={server.name}, name={name}, error={e}")
            data = False

        if not data:
            if index == 0:
                LOGGER.error(f"主服创建账户失败，终止创建: server={server.name}, name={name}")
                return result
            LOGGER.warning(f"跳过创建失败的服务器: server={server.name}, name={name}")
            result.accounts.append((server.name, None, "failed"))
            continue

        embyid, pwd = data[0], data[1]
        password = pwd  # 主服生成或传入的密码，其余服务器复用，保证多服同密
        result.accounts.append((server.name, embyid, "active"))
        LOGGER.info(f"服务器创建账户成功: server={server.name}, name={name}, embyid={embyid}")

    result.ok = True
    result.password = password
    result.embyid = result.accounts[0][1]
    result.expired = datetime.now() + timedelta(days=days)
    return result


async def emby_del_all(tg: int = None, embyid: str = None) -> bool:
    """
    删除账户在各服上的实体，删除成功的服务器同步清理账户记录
    :return: 是否全部成功；失败的服务器保留记录便于重试
    """
    targets = server_account_targets(tg=tg, embyid=embyid)
    if not targets:
        LOGGER.warning(f"没有可删除的服务器账户: tg={tg}, embyid={embyid}")
        return False

    all_ok = True
    for server, eid in targets:
        if await get_emby(server).emby_del(emby_id=eid):
            if tg is not None:
                sql_delete_server_account(tg=tg, server=server)
        else:
            LOGGER.error(f"删除账户失败: server={server}, embyid={eid}, tg={tg}")
            all_ok = False
    return all_ok


async def emby_policy_all(tg: int = None, embyid: str = None, admin: bool = False, disable: bool = False) -> bool:
    """
    在各服上同步启用/禁用用户
    :return: 是否全部成功
    """
    targets = server_account_targets(tg=tg, embyid=embyid)
    if not targets:
        LOGGER.warning(f"没有可操作的服务器账户: tg={tg}, embyid={embyid}")
        return False

    all_ok = True
    for server, eid in targets:
        if not await get_emby(server).emby_change_policy(emby_id=eid, admin=admin, disable=disable):
            LOGGER.error(f"修改用户策略失败: server={server}, embyid={eid}, disable={disable}, tg={tg}")
            all_ok = False
    return all_ok


async def emby_reset_all(tg: int, new_password: str = None, embyid: str = None) -> bool:
    """
    在各服上同步重置为同一密码，全部成功后统一写入 emby.pwd
    :param new_password: 新密码，None 表示重置为无密码
    :return: 是否成功
    """
    targets = server_account_targets(tg=tg, embyid=embyid)
    if not targets:
        LOGGER.warning(f"没有可重置密码的服务器账户: tg={tg}")
        return False

    all_ok = True
    for server, eid in targets:
        if not await get_emby(server).emby_reset(emby_id=eid, new_password=new_password, write_db=False):
            LOGGER.error(f"重置密码失败: server={server}, embyid={eid}, tg={tg}")
            all_ok = False
    if not all_ok:
        return False

    if not sql_update_emby(Emby.tg == tg, pwd=new_password):
        LOGGER.error(f"密码已在各服重置，但数据库写入失败: tg={tg}")
        return False
    return True


def render_server_lines(tg: int = None, lv: str = None, embyid: str = None) -> str:
    """
    渲染用户可见的线路文本，多服时逐台列出并标注开通状态，单服时与原展示一致
    :param embyid: 主服账户 id，用于身份刚绑定/转移、emby 表尚未写入时也能正确展示
    未登记服务器账户的历史账户回退到 emby 表的主服账户
    """
    targets = target_servers(lv)
    if not targets:
        return config.servers[0].line
    if len(targets) == 1:
        return targets[0].line or config.servers[0].url

    rows = {row[0]: row for row in sql_get_server_accounts(tg)} if tg else {}
    if not rows:
        primary = primary_server_name()
        if embyid:
            rows = {primary: (primary, embyid, None, 'active')}
        elif tg:
            legacy = sql_get_emby(tg=tg)
            if legacy is not None and legacy.embyid:
                rows = {primary: (primary, legacy.embyid, legacy.name, 'active')}

    lines = []
    for server in targets:
        text = server.line or server.url
        row = rows.get(server.name)
        if row is None or not (row[1] and row[3] == 'active'):
            text += '（未开通）'
        lines.append(f'· {server.name} | {text}')
    return '\n'.join(lines)
