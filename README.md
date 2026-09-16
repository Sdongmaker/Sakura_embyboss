# 🌸 Sakura_embyboss 初学练习版（重构中）

<p align="center">
<img src="image/bot2.png" alt="bot"><br>
<a href="https://github.com/berry8838/Sakura_embyboss/stargazers"><img src="https://img.shields.io/github/stars/berry8838/Sakura_embyboss" alt="stars"></a> 
<a href="https://github.com/berry8838/Sakura_embyboss/forks"><img src="https://img.shields.io/github/forks/berry8838/Sakura_embyboss" alt="forks"></a> 
<a href="https://github.com/berry8838/Sakura_embyboss/issues"><img src="https://img.shields.io/github/issues/berry8838/Sakura_embyboss" alt="issue"></a>  
<a href="https://github.com/berry8838/Sakura_embyboss/blob/master/LICENSE"><img src="https://img.shields.io/github/license/berry8838/Sakura_embyboss" alt="license"></a> 
<a href="https://hub.docker.com/r/jingwei520/sakura_embyboss" ><img src="https://img.shields.io/docker/v/jingwei520/sakura_embyboss/latest?logo=docker" alt="docker"></a>
<a href="https://hub.docker.com/r/jingwei520/sakura_embyboss/tags" ><img src="https://img.shields.io/badge/platform-amd64%20arm64-pink" alt="plat"></a>
<a href="https://github.com/berry8838/Sakura_embyboss/actions/workflows/publish-docker_on_master.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/berry8838/Sakura_embyboss/publish-docker_on_master.yml?branch=master" alt="Build status" />
</a>
</p>
<br>

## 📜 项目说明（重构中，暂停更新）

- **用Telegram管理Emby用户**（开服） 安装使用 👉 [项目文档](https://berry8838.github.io/Sakura_embyboss)
- **推荐使用 Debian 11操作系统，AMD处理器架构。目前ARM也支持（如有问题请反馈issue）**
- 解决不了大的技术问题（因为菜菜），如需要，请自行fork修改，~~如果能提点有意思的pr更好啦~~
- 反馈请尽量 issue，看到会处理

> **声明：本项目仅供学习交流使用，仅作为辅助工具借助tg平台方便用户管理自己的媒体库成员，对用户的其他行为及内容毫不知情**
<br>

## 🖥️ 多服务器（多台 Emby 统一纳管）

`config.json` 中的 `servers` 支持同时纳管多台 Emby，用户在每台上使用**同一个用户名和同一个密码**，面板会逐台列出各自线路。

```jsonc
"servers": [
  { "name": "main", "url": "http://10.0.0.1:8096", "api": "主服密钥", "line": "https://a.example.com" },
  { "name": "srv2", "url": "http://10.0.0.2:8096", "api": "备用密钥", "line": "https://b.example.com" },
  { "name": "srv3", "url": "http://10.0.0.3:8096", "api": "三号密钥", "line": "https://c.example.com",
    "lvs": ["a", "b"], "block_libs": [] }
]
```

- `servers[0]` 为主服，`emby` 表中的 `embyid/pwd/name` 记录主服账户；`emby_url/emby_api/emby_line` 作为其兼容别名保留。
- **不配置 `servers` 时行为与单服完全一致**：自动由 `emby_url/emby_api/emby_line` 合成一台 `main`。
- 密码生成规则未改动：注册时主服按原逻辑生成 8 位密码，其余服务器复用同一密码；用户改密、签到续期、封禁/解封、删号（面板、`/kk`、`rmemby`、`/uinfo`、退群删号、定时任务）都会同步到所有服务器。
- 注册时单台失败只标记该台「未开通」不阻塞，主服失败才算整体失败；删除某台失败会保留记录以便重试。
- `lvs`：注册时允许在该服建号的等级，例如 `["a"]` 表示只有白名单用户会在这台建号，留空表示所有等级都开通（升级到更高等级后如需补开，管理员可在该服手动建号）；`block_libs`：该服建号后额外隐藏的媒体库，留空用全局 `emby_block + extra_emby_libs`（策略兜底屏蔽项仍由全局设置决定）；`line` 是展示给用户的该服访问地址。
- **同步失败的判定**：封禁/解封/改密/删号以「所有已开通服务器都成功」为成功；某台失败时不写库并提示失败，保留记录待下次重试，避免出现「面板显示旧密码、某台仍是新密码」的错配。
- 已开通状态记录在 `emby_server_accounts`（`(tg, server)` 复合主键），首次升级会自动把现存 `emby` 表的账户回填到主服。
- 改 `servers` 的 `url/api` 后需重启 bot（与 `emby_url/emby_api` 行为一致）；`line` 通过配置面板修改后立即生效。

**已知边界**：非 TG 账户（`/ucr`、`emby2` 表）、用户自助绑定/换绑（`bindtg`）仅在主服生效；webhook 风控（`line_report`/`client_filter`）与播放榜单按主服运行；`/syncunbound`（清理未绑定账户）以主服用户列表为基准。

<br>

## 💐 Our Contributors

<a href="https://github.com/berry8838/Sakura_embyboss/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=berry8838/Sakura_embyboss" />
</a>  

## 特别感谢（排序不分先后）<img src="image/bixin.jpg" alt="比心" height=30>

- [Pyrogram • 一个现代、优雅和异步的MTProto API框架](https://github.com/pyrogram/pyrogram)
- [Nezha探针 • 自托管、轻量级、服务器和网站监控运维工具](https://github.com/naiba/nezha)
- [小宝 • 按钮风格](https://t.me/EmbyClubBot)
- [MisakaF_Emby • 启发](https://github.com/MisakaFxxk/MisakaF_Emby)
  以及  [EMBY API官方文档](https://swagger.emby.media/?staticview=true#/UserService)
- [Nolovenodie • 播放榜单海报推送借鉴](https://github.com/Nolovenodie/EmbyTools)
- [罗宝 • 提供的代码援助](https://github.com/dddddluo)
- [折花 • 日榜周榜推送设计图](https://github.com/U41ovo)<br>


## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=berry8838/Sakura_embyboss&type=Date)](https://star-history.com/#berry8838/Sakura_embyboss)