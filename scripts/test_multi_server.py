#!/usr/bin/env python3
"""
多服务器统一纳管行为测试（不依赖数据库与真实 Emby）

依赖注入方式与 scripts/test_emby_policy.py 一致：把 bot / aiohttp / sql_helper 换成内存桩，
被测试的是真实的多服实现（bot/func_helper/emby.py）。

覆盖契约：
1. 注册时主服生成的密码被其余服务器复用，pwd_create 只调用一次
2. 单台建号失败只标记 failed 不阻塞；主服失败整体失败且不残留账户
3. 封禁/解封、改密、删除在所有服务器同步执行
4. 删除部分失败时保留该服记录便于重试；账户已不存在时删除幂等
5. 线路渲染逐台列出并标注未开通，单服时与原展示一致
"""
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "bot"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 内存中的 emby_server_accounts / emby 表
SERVER_ACCOUNTS = {}
LEGACY_EMBY = {}
UPDATED_ROWS = []
PWD_CREATE_CALLS = []
TEST_TG = 1001


def install_test_stubs():
    aiohttp_stub = types.ModuleType("aiohttp")

    class ClientTimeout:
        def __init__(self, total=None, connect=None):
            self.total = total
            self.connect = connect

    class ClientSession:
        def __init__(self, *args, **kwargs):
            self.closed = False

        async def close(self):
            self.closed = True

    aiohttp_stub.ClientTimeout = ClientTimeout
    aiohttp_stub.ClientSession = ClientSession
    sys.modules["aiohttp"] = aiohttp_stub

    class ServerCfg:
        def __init__(self, name, url, api, line="", lvs=None, block_libs=None):
            self.name = name
            self.url = url
            self.api = api
            self.line = line
            self.lvs = lvs
            self.block_libs = block_libs

    schemas_stub = types.ModuleType("bot.schemas")
    schemas_stub.ServerCfg = ServerCfg
    sys.modules["bot.schemas"] = schemas_stub

    log = types.SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
        exception=lambda *a, **k: None,
    )

    config_stub = types.SimpleNamespace(
        servers=[
            ServerCfg("main", "http://main.local", "token-main", "https://main.line"),
            ServerCfg("srv2", "http://srv2.local", "token-srv2", "https://srv2.line"),
            ServerCfg("srv3", "http://srv3.local", "token-srv3", "https://srv3.line", lvs=["a", "b"]),
        ]
    )

    bot_stub = types.ModuleType("bot")
    bot_stub.__path__ = [str(BOT_DIR)]
    bot_stub.emby_url = "http://main.local"
    bot_stub.emby_api = "token-main"
    bot_stub.emby_block = ["播放列表"]
    bot_stub.extra_emby_libs = ["额外库"]
    bot_stub.LOGGER = log
    bot_stub.config = config_stub
    sys.modules["bot"] = bot_stub

    sql_emby_stub = types.ModuleType("bot.sql_helper.sql_emby")
    sql_emby_stub.Emby = types.SimpleNamespace(tg="tg", embyid="embyid")

    def sql_update_emby(condition, **kwargs):
        UPDATED_ROWS.append(kwargs)
        return True

    def sql_get_emby(tg=None):
        return LEGACY_EMBY.get(tg)

    def sql_add_server_account(tg, server, embyid, name=None, status="active"):
        SERVER_ACCOUNTS.setdefault(tg, {})[server] = (server, embyid, name, status)
        return True

    def sql_get_server_accounts(tg):
        return [tuple(row) for row in SERVER_ACCOUNTS.get(tg, {}).values()]

    def sql_delete_server_account(tg=None, server=None):
        if server is None:
            SERVER_ACCOUNTS.pop(tg, None)
        else:
            SERVER_ACCOUNTS.get(tg, {}).pop(server, None)
        return True

    sql_emby_stub.sql_update_emby = sql_update_emby
    sql_emby_stub.sql_get_emby = sql_get_emby
    sql_emby_stub.sql_add_server_account = sql_add_server_account
    sql_emby_stub.sql_get_server_accounts = sql_get_server_accounts
    sql_emby_stub.sql_delete_server_account = sql_delete_server_account
    sys.modules["bot.sql_helper.sql_emby"] = sql_emby_stub

    utils_stub = types.ModuleType("bot.func_helper.utils")

    async def pwd_create(length):
        PWD_CREATE_CALLS.append(length)
        return "gen-pwd"

    class CacheStub:
        def memoize(self, ttl=None):
            def decorator(func):
                return func

            return decorator

    class Singleton(type):
        _instances = {}

        def __call__(cls, *args, **kwargs):
            key = (cls, args, frozenset(kwargs.items()))
            if key not in cls._instances:
                cls._instances[key] = super(Singleton, cls).__call__(*args, **kwargs)
            return cls._instances[key]

    utils_stub.pwd_create = pwd_create
    utils_stub.convert_runtime = lambda value: value
    utils_stub.cache = CacheStub()
    utils_stub.Singleton = Singleton
    sys.modules["bot.func_helper.utils"] = utils_stub


install_test_stubs()
from bot.func_helper import emby as emby_module  # noqa: E402
from bot.func_helper.emby import (  # noqa: E402
    EmbyApiResult,
    emby_pool,
    emby_create_all,
    emby_del_all,
    emby_policy_all,
    emby_reset_all,
    render_server_lines,
    target_servers,
)


class FakeEmbyServer:
    """模拟一台 Emby：用户名唯一、按 id 维护密码与策略、删除缺失账户返回 404"""

    def __init__(self, label):
        self.label = label
        self.users = {}
        self.seq = 0
        self.fail_delete = False

    def add_user(self, name, password=None):
        self.seq += 1
        user_id = f"{self.label}-{self.seq}"
        self.users[user_id] = {"Name": name, "Pw": password, "Policy": {}}
        return user_id

    def password_of(self, name):
        for user in self.users.values():
            if user["Name"] == name:
                return user["Pw"]
        return "<missing>"

    def disabled_of(self, name):
        for user in self.users.values():
            if user["Name"] == name:
                return bool(user["Policy"].get("IsDisabled"))
        return None

    async def request(self, method, endpoint, **kwargs):
        payload = kwargs.get("json") or {}
        parts = [part for part in endpoint.split("/") if part]
        if method == "POST" and endpoint == "/emby/Users/New":
            name = payload.get("Name")
            if any(user["Name"] == name for user in self.users.values()):
                return EmbyApiResult(False, error="HTTP 400")
            return EmbyApiResult(True, {"Id": self.add_user(name)})
        if len(parts) >= 3 and parts[:2] == ["emby", "Users"]:
            user_id, rest = parts[2], parts[3:]
            if method == "POST" and rest == ["Password"]:
                if user_id not in self.users:
                    return EmbyApiResult(False, error="资源不存在")
                self.users[user_id]["Pw"] = payload.get("NewPw")
                return EmbyApiResult(True, b"")
            if method == "POST" and rest == ["Policy"]:
                if user_id not in self.users:
                    return EmbyApiResult(False, error="资源不存在")
                self.users[user_id]["Policy"] = payload
                return EmbyApiResult(True, b"")
            if method == "DELETE":
                if user_id not in self.users:
                    return EmbyApiResult(False, error="资源不存在")
                if self.fail_delete:
                    return EmbyApiResult(False, error="HTTP 500")
                del self.users[user_id]
                return EmbyApiResult(True, b"")
            if method == "GET":
                user = self.users.get(user_id)
                if user is None:
                    return EmbyApiResult(False, error="资源不存在")
                return EmbyApiResult(True, {"Id": user_id, "Name": user["Name"], "Policy": user["Policy"]})
        return EmbyApiResult(False, error=f"unexpected {method} {endpoint}")


class MultiServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SERVER_ACCOUNTS.clear()
        LEGACY_EMBY.clear()
        UPDATED_ROWS.clear()
        PWD_CREATE_CALLS.clear()
        self.servers = {label: FakeEmbyServer(label) for label in ("main", "srv2", "srv3")}
        for name, service in emby_pool.items():
            service._request = self.servers[name].request

    async def asyncTearDown(self):
        for service in emby_pool.values():
            await service.close()

    async def register(self, name, days=30, lv="b", tg=TEST_TG):
        """复刻 register_queue 的写法：建号后登记各服账户"""
        result = await emby_create_all(name=name, days=days, lv=lv)
        for server, embyid, status in result.accounts:
            emby_module.sql_add_server_account(tg, server, embyid, name, status)
        return result

    async def test_create_all_reuses_primary_password_on_every_server(self):
        result = await self.register("alice")

        self.assertTrue(result.ok)
        self.assertEqual(result.password, "gen-pwd")
        self.assertEqual(PWD_CREATE_CALLS, [8], "密码生成方式保持原样，且只在主服生成一次")
        self.assertEqual(
            result.accounts,
            [("main", "main-1", "active"), ("srv2", "srv2-1", "active"), ("srv3", "srv3-1", "active")],
        )
        self.assertEqual(result.embyid, "main-1")
        for server in self.servers.values():
            self.assertEqual(server.password_of("alice"), "gen-pwd", f"{server.label} 密码与主服不一致")

    async def test_create_all_marks_failed_secondary_without_blocking(self):
        self.servers["srv2"].add_user("bob")

        result = await self.register("bob", days=7)

        self.assertTrue(result.ok)
        self.assertEqual(
            result.accounts,
            [("main", "main-1", "active"), ("srv2", None, "failed"), ("srv3", "srv3-1", "active")],
        )
        self.assertEqual(self.servers["srv3"].password_of("bob"), "gen-pwd")
        self.assertEqual(SERVER_ACCOUNTS[TEST_TG]["srv2"], ("srv2", None, "bob", "failed"))
        self.assertEqual(SERVER_ACCOUNTS[TEST_TG]["main"][1], "main-1")

    async def test_create_all_fails_whole_job_when_primary_fails(self):
        self.servers["main"].add_user("carol")

        result = await self.register("carol", days=7)

        self.assertFalse(result.ok)
        self.assertIsNone(result.password)
        self.assertEqual(result.accounts, [])
        self.assertEqual(self.servers["srv2"].users, {})
        self.assertEqual(self.servers["srv3"].users, {})

    async def test_create_all_skips_servers_out_of_user_level(self):
        self.assertEqual([server.name for server in target_servers("b")], ["main", "srv2", "srv3"])
        self.assertEqual([server.name for server in target_servers("d")], ["main", "srv2"])

        self.servers["srv2"].add_user("dave")
        result = await self.register("dave", days=7, lv="d")

        self.assertTrue(result.ok)
        self.assertEqual(result.accounts, [("main", "main-1", "active"), ("srv2", None, "failed")])

    async def test_policy_reset_and_delete_fan_out_to_all_servers(self):
        result = await self.register("erin")

        self.assertTrue(await emby_policy_all(tg=TEST_TG, embyid=result.embyid, disable=True))
        for server in self.servers.values():
            self.assertTrue(server.disabled_of("erin"), f"{server.label} 未同步禁用")

        self.assertTrue(await emby_policy_all(tg=TEST_TG, embyid=result.embyid, disable=False))
        for server in self.servers.values():
            self.assertFalse(server.disabled_of("erin"), f"{server.label} 未同步解禁")

        UPDATED_ROWS.clear()
        self.assertTrue(await emby_reset_all(tg=TEST_TG, new_password="new-pwd"))
        for server in self.servers.values():
            self.assertEqual(server.password_of("erin"), "new-pwd", f"{server.label} 未同步新密码")
        self.assertEqual([row.get("pwd") for row in UPDATED_ROWS], ["new-pwd"], "改密后只应写一次 emby.pwd")

        self.assertTrue(await emby_reset_all(tg=TEST_TG))
        for server in self.servers.values():
            self.assertIsNone(server.password_of("erin"), f"{server.label} 未同步清空密码")
        self.assertEqual([row.get("pwd") for row in UPDATED_ROWS][-1], None)

        self.assertTrue(await emby_del_all(tg=TEST_TG, embyid=result.embyid))
        for server in self.servers.values():
            self.assertEqual(server.users, {}, f"{server.label} 未同步删除")
        self.assertEqual(SERVER_ACCOUNTS.get(TEST_TG), {})

    async def test_delete_keeps_failed_server_row_for_retry(self):
        result = await self.register("frank")
        self.servers["srv3"].fail_delete = True

        self.assertFalse(await emby_del_all(tg=TEST_TG, embyid=result.embyid))
        self.assertEqual([row[0] for row in SERVER_ACCOUNTS[TEST_TG].values()], ["srv3"], "失败的服务器应保留记录便于重试")
        self.assertEqual(list(self.servers["srv3"].users), ["srv3-1"])

        self.servers["srv3"].fail_delete = False
        self.assertTrue(await emby_del_all(tg=TEST_TG, embyid=result.embyid))
        self.assertEqual(SERVER_ACCOUNTS.get(TEST_TG), {})
        for server in self.servers.values():
            self.assertEqual(server.users, {})

    async def test_delete_is_idempotent_for_missing_account(self):
        self.assertTrue(await emby_del_all(embyid="ghost"), "账户已不存在时应视为删除成功")

    async def test_render_lines_lists_each_server_with_provision_state(self):
        await self.register("grace")
        SERVER_ACCOUNTS[TEST_TG]["srv2"] = ("srv2", None, "grace", "failed")

        text = render_server_lines(TEST_TG, "b")

        self.assertIn("main | https://main.line", text)
        self.assertIn("srv2 | https://srv2.line（未开通）", text)
        self.assertIn("srv3 | https://srv3.line", text)
        self.assertNotIn("srv3 | https://srv3.line（未开通）", text)

    async def test_render_lines_keeps_single_server_display(self):
        original = emby_module.config.servers
        emby_module.config.servers = [original[0]]
        try:
            self.assertEqual(render_server_lines(TEST_TG, "b"), "https://main.line")
        finally:
            emby_module.config.servers = original

    async def test_render_lines_falls_back_to_emby_table_for_legacy_account(self):
        LEGACY_EMBY[TEST_TG] = types.SimpleNamespace(embyid="legacy-1", name="heidi", lv="b")

        text = render_server_lines(TEST_TG, "b")

        self.assertIn("main | https://main.line", text)
        self.assertNotIn("main | https://main.line（未开通）", text)
        self.assertIn("srv2 | https://srv2.line（未开通）", text)

    async def test_render_lines_accepts_explicit_primary_id_before_db_write(self):
        # 绑定/换绑场景：emby 表尚未写入 embyid，也应正确展示主服已开通
        text = render_server_lines(TEST_TG, "b", "fresh-bind-id")

        self.assertIn("main | https://main.line", text)
        self.assertNotIn("main | https://main.line（未开通）", text)
        self.assertIn("srv2 | https://srv2.line（未开通）", text)

    async def test_render_lines_marks_missing_server_without_any_account(self):
        text = render_server_lines(TEST_TG, "b")

        self.assertIn("main | https://main.line（未开通）", text)
        self.assertIn("srv2 | https://srv2.line（未开通）", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
