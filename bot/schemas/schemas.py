import json
import os
import secrets
from pydantic import BaseModel, Field
from typing import List, Optional, Union

MAX_INT_VALUE = 2147483647
MIN_INT_VALUE = -2147483648


class ExDate(BaseModel):
    mon: int = 30
    sea: int = 90
    half: int = 180
    year: int = 365
    used: int = 0
    unused: int = -1
    code: str = "code"
    link: str = "link"


class Open(BaseModel):
    """Settings retained for renewal, whitelist and moderation flows."""
    exchange: bool = True
    use_whitelist_code: bool = True
    leave_ban: bool = True


class Ranks(BaseModel):
    logo: str = "SAKURA"
    backdrop: bool = False


class Schedall(BaseModel):
    dayrank: bool = True
    weekrank: bool = True
    dayplayrank: bool = False
    weekplayrank: bool = True
    check_ex: bool = True
    low_activity: bool = False
    day_ranks_message_id: int = 0
    week_ranks_message_id: int = 0
    restart_chat_id: int = 0
    restart_msg_id: int = 0
    backup_db: bool = True

    def __init__(self, **data):
        super().__init__(**data)
        if self.day_ranks_message_id == 0 or self.week_ranks_message_id == 0:
            if os.path.exists("log/rank.json"):
                with open("log/rank.json", "r", encoding="utf-8") as f:
                    values = json.load(f)
                    self.day_ranks_message_id = values.get("day_ranks_message_id", 0)
                    self.week_ranks_message_id = values.get("week_ranks_message_id", 0)


class Proxy(BaseModel):
    scheme: Optional[str] = ""
    hostname: Optional[str] = ""
    port: Optional[int] = None
    username: Optional[str] = ""
    password: Optional[str] = ""


class MP(BaseModel):
    status: bool = False
    url: Optional[str] = ""
    username: Optional[str] = ""
    password: Optional[str] = ""
    access_token: Optional[str] = ""
    download_log_chatid: Optional[int] = None
    lv: Optional[str] = "b"


class AutoUpdate(BaseModel):
    status: bool = True
    git_repo: Optional[str] = "berry8838/Sakura_embyboss"
    commit_sha: Optional[str] = None
    up_description: Optional[str] = None


class API(BaseModel):
    status: bool = False
    http_url: Optional[str] = "0.0.0.0"
    http_port: Optional[int] = 8838
    allow_origins: Optional[List[Union[str, int]]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.allow_origins is None:
            self.allow_origins = ["*"]


class ServerCfg(BaseModel):
    """单台 Emby 服务器配置，servers[0] 为主服。"""
    name: str
    url: str
    api: str
    line: Optional[str] = ""
    lvs: Optional[List[str]] = None


class Shop(BaseModel):
    """dujiao-next upstream credentials and public connection settings."""
    enabled: bool = True
    listen_host: str = "127.0.0.1"
    listen_port: int = 8838
    api_key: str = Field(default_factory=lambda: secrets.token_urlsafe(24))
    api_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    site_name: str = "Sakura Emby"
    url: str = ""


class Config(BaseModel):
    bot_name: str
    bot_token: str
    owner_api: int
    owner_hash: str
    owner: int
    group: List[int]
    main_group: str
    chanel: str
    bot_photo: str
    open: Open = Field(default_factory=Open)
    admins: List[int] = Field(default_factory=list)
    emby_api: str
    emby_url: str
    emby_line: str
    db_host: str
    db_user: str
    db_pwd: str
    db_name: str
    db_port: int = 3306
    tz_ad: Optional[str] = None
    tz_api: Optional[str] = None
    tz_id: List[Union[int, str]] = Field(default_factory=list)
    tz_version: Optional[str] = "v0"
    tz_username: Optional[str] = None
    tz_password: Optional[str] = None
    ranks: Ranks = Field(default_factory=Ranks)
    schedall: Schedall = Field(default_factory=Schedall)
    db_is_docker: bool = False
    db_docker_name: str = "mysql"
    db_backup_dir: str = "./db_backup"
    db_backup_maxcount: int = 7
    w_anti_channel_ids: List[Union[str, int]] = Field(default_factory=list)
    proxy: Optional[Proxy] = Field(default_factory=Proxy)
    fuxx_pitao: bool = True
    activity_check_days: int = 21
    freeze_days: int = 5
    emby_whitelist_line: Optional[str] = None
    client_filter_enabled: bool = False
    blocked_clients: Optional[List[str]] = None
    client_filter_mode: str = "blacklist"
    allowed_clients: Optional[List[str]] = None
    client_filter_terminate_session: bool = True
    client_filter_block_user: bool = False
    line_filter_terminate_session: bool = True
    line_filter_block_user: bool = False
    moviepilot: MP = Field(default_factory=MP)
    auto_update: AutoUpdate = Field(default_factory=AutoUpdate)
    api: API = Field(default_factory=API)
    shop: Shop = Field(default_factory=Shop)
    servers: Optional[List[ServerCfg]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.owner in self.admins:
            self.admins.remove(self.owner)
        if not self.servers:
            self.servers = [ServerCfg(name="main", url=self.emby_url, api=self.emby_api, line=self.emby_line)]
        elif len({server.name for server in self.servers}) != len(self.servers):
            raise ValueError("config.servers 中的 name 必须唯一")

    @classmethod
    def load_config(cls):
        with open("config.json", "r", encoding="utf-8") as f:
            return cls(**json.load(f))

    def save_config(self):
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=4, ensure_ascii=False)
