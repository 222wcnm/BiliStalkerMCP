# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![PyPI version](https://badge.fury.io/py/bili-stalker-mcp.svg)](https://pypi.org/project/bili-stalker-mcp/)

## 面向指定 B 站用户分析的 Bilibili MCP Server

BiliStalkerMCP 是一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 的 Bilibili MCP Server，专门面向需要分析指定 B 站用户或 UP 主的 AI 助手。

它的工作流默认从目标 uid 或用户名出发，再结构化获取该用户的档案、视频、动态、专栏、字幕与关注列表。

如果你在查找 Bilibili MCP、哔哩哔哩 MCP、B 站 MCP Server，或用于追踪与分析指定 B 站用户的 Model Context Protocol 服务，这个仓库就是为这些场景设计的。

**[English](README.md) | 中文说明**

## 🚀 快速开始

### 安装

```bash
uvx bili-stalker-mcp
# 或
pip install bili-stalker-mcp
```

### 配置 (Claude Desktop，推荐)

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/BiliStalkerMCP", "bili-stalker-mcp"],
      "env": {
        "SESSDATA": "必填_SESSDATA",
        "BILI_JCT": "可选_BILI_JCT",
        "BUVID3": "可选_BUVID3"
      }
    }
  }
}
```

> 当 PyPI 包更新传播较慢时，优先使用 `uv run --directory ...` 直接跑本地仓库版本。
> `uvx bili-stalker-mcp` 仍可用于快速一次性体验。

> **凭据获取**: 在 B 站网页端按下 F12 -> Application -> Cookies 中获取相关值。

### 环境变量

| 变量名 | 必填 | 描述 |
|--------|:----:|------|
| `SESSDATA` | 条件必填 | B 站登录凭证；未通过 `BILI_COOKIE_FILE` 提供时必填。 |
| `BILI_JCT` | 否 | CSRF Token，涉及高权限操作时必需。 |
| `BUVID3` | 否 | 硬件指纹，显著降低风控阻断风险。 |
| `BILI_COOKIE_FILE` | 否 | 普通 Cookie 文件路径。 |
| `BILI_REFRESH_TOKEN_FILE` | 否 | 独立 refresh token 文件路径；不得通过环境变量提供 token。 |
| `BILI_ENABLE_COOKIE_REFRESH` | 否 | 设为 `true` 后启用安全自动刷新；默认：`false`。 |
| `BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS` | 否 | 检查刷新需求的间隔秒数；默认：`21600`，最小：`60`。 |
| `BILI_LOG_LEVEL` | 否 | 映射至 `DEBUG`, `INFO` (默认), `WARNING`。 |
| `BILI_TIMEZONE` | 否 | 格式化时间输出时区（默认：`Asia/Shanghai`）。 |

### 可选的安全 Cookie 自动刷新

自动刷新默认关闭。只有当 Cookie 文件和 refresh token 文件均为已存在、可读、可写的
普通文件时才应启用。Cookie 文件只能包含普通 Cookie（`SESSDATA`、`bili_jct`、
`buvid3`、`buvid4`、`DedeUserID`）；refresh token 只能写在独立文件中。

```json
{
  "BILI_COOKIE_FILE": "/secure/bilibili-cookie.txt",
  "BILI_REFRESH_TOKEN_FILE": "/secure/bilibili-refresh-token.txt",
  "BILI_ENABLE_COOKIE_REFRESH": "true",
  "BILI_COOKIE_REFRESH_CHECK_INTERVAL_SECONDS": "21600"
}
```

启用刷新后，不要再通过环境变量设置 `SESSDATA`、`BILI_JCT` 或 `DEDEUSERID`：这些会
轮换的值必须来自 Cookie 文件，避免重启后重新加载旧凭据。`BUVID3` 和 `BUVID4` 仍可由
环境变量提供。检查会按间隔执行，共享这些文件的并发 MCP 调用和多个服务进程会共用刷新锁；
存在 pending-confirm 状态时会先恢复确认，不会直接产生另一组凭据。锁的旁路文件名为
`.bili-cookie-refresh.lock`，进程退出后保留属于正常现象。

如需更快完成首次配置，可从 B 站浏览器请求中复制完整 Cookie header 的值，再从 Local
Storage 复制 `ac_time_value`，然后运行：

```powershell
uv run bili-stalker-cookie-setup --directory D:\BiliStalkerSecrets
```

如果只从 PyPI 调用、不克隆仓库，可以运行：

```powershell
uvx --from bili-stalker-mcp bili-stalker-cookie-setup --directory D:\BiliStalkerSecrets
```

脚本会隐藏两次粘贴输入，拒绝写入仓库内目录或覆盖已有凭据文件，并且只输出不含 secret 的
MCP `env` 配置片段。不要粘贴完整 cURL 命令，只粘贴其中 `cookie:` 后面的值。

### 本地验证

以下命令均使用 mock，不需要也不应填入 B 站真实凭据：

```powershell
uv run pytest -q tests/test_credentials.py tests/test_cookie_refresh.py tests/test_tool_contract.py
uv run pytest -q
uv run black --check bili_stalker_mcp tests scripts
uv run isort --check-only bili_stalker_mcp tests scripts
uv run flake8 bili_stalker_mcp tests scripts
uv run mypy bili_stalker_mcp
```

## 🛠️ 工具集

| 工具 | 功能描述 | 参数 |
|------|----------|------|
| `get_user_info` | 档案资料与核心统计数据 | `user_id_or_username` |
| `get_user_videos` | 轻量视频列表 | `user_id_or_username`, `page`, `limit` |
| `search_user_videos` | 指定用户视频关键词检索 | `user_id_or_username`, `keyword`, `page`, `limit` |
| `get_video_detail` | 视频详情与可选字幕聚合 | `bvid`, `fetch_subtitles`（默认：`false`）, `subtitle_mode`（`smart`/`full`/`minimal`）, `subtitle_lang`（默认：`auto`）, `subtitle_max_chars` |
| `get_user_dynamics` | 含图片元数据的结构化动态流（Cursor 分页） | `user_id_or_username`, `cursor`, `limit`, `dynamic_type` |
| `get_user_articles` | 轻量专栏列表 | `user_id_or_username`, `page`, `limit` |
| `get_article_content` | 专栏 Markdown 全文 | `article_id` |
| `get_user_followings` | 用户关注列表分析 | `user_id_or_username`, `page`, `limit` |
| `get_content_comments` | 视频、专栏或动态的评论（含图片和笔记元数据） | `content_type`, `content_id`, `cursor`, `limit`, `sort` |
| `get_content_comment_replies` | 视频、专栏或动态评论的完整楼中楼回复 | `content_type`, `content_id`, `root_rpid`, `page`, `limit` |

评论中的 `pictures` 会保留原始图片 URL。普通长评论保留 B 站接口返回的完整文本；
笔记类型长评可能只返回预览，可将返回的 `note.cvid` 交给 `get_article_content` 获取全文。
获取视频评论时，将 `content_type` 设为 `video`，并把 BVID、AV 号或视频 URL 作为
`content_id`。需要完整楼中楼时，将主评论的 `rpid` 作为 `root_rpid` 传入。

### 动态类型过滤 (`dynamic_type`)

- `ALL` (默认): 仅文本、图文（DRAW）、转发（最适合 AI 分析）。
- `ALL_RAW`: 原始全量数据（包含视频及专栏）。
- `VIDEO`, `ARTICLE`, `DRAW`, `TEXT`: 特定分类过滤。
- `REVIEW`: 仅返回项目已识别的五格星级评分卡。结果中的 `review.rating` 是已点亮
  星数（0-5），并会返回 `review.title`、`review.text`、封面与跳转 URL，以及可用的
  来源评分说明；该过滤器不会自行判断被评分的标题是否属于动漫。

每条动态都包含 `images` 列表，图片对象提供 `url`、`width` 和 `height`；
无有效 URL 的图片会被过滤，无法解析的尺寸返回 `null`。`image_count` 始终等于
实际返回的图片数量。转发动态在 `origin.images` 和 `origin.image_count` 中提供
相同字段；无图片动态的 `images` 为空列表。

**分页机制**: 响应包含 `next_cursor`。后续请求传入此参数可实现连续拉取。

### 字幕模式 (`get_video_detail`)

- `smart`（`fetch_subtitles=true` 时默认）: 拉取全部分P字幕元数据，但仅下载 1 条最优匹配字幕正文。
- `full`: 下载所有字幕轨正文（开销较高）。
- `minimal`: 跳过字幕元数据与正文拉取。

`subtitle_lang` 可指定语言（如 `en-US`）；`auto` 会按内置优先级自动回退。  
`subtitle_max_chars` 可限制字幕正文最大返回字符数，避免 token 膨胀。

## 📎 附带 Skill

仓库内置一个可直接使用的 AI Agent Skill，位于 `skills/bili-content-analysis/`：

```
skills/bili-content-analysis/
├── SKILL.md                        # 工作流与输出规范
└── references/
    └── analysis-style.md           # 深度分析写作风格指南
```

### 功能

引导兼容的 AI Agent（Gemini、Claude 等）执行结构化的 6 步 B 站内容分析流程：

1. **明确目标** — 提取 uid / bvid / 关键词等标识符。
2. **最小采集** — 优先调用轻量列表工具，仅对高价值条目拉取详情。
3. **重建原文** — 按时间线、章节或原始逻辑顺序还原源材料结构。
4. **构建分析** — 梳理事实、逻辑链、假设、主题与近期转向。
5. **保留锚点** — 输出中保留 uid、bvid、article_id、时间戳及关键原文片段。
6. **安全降级** — 数据缺失时明确阻塞原因，拒绝臆测。

### 使用方式

将 `bili-content-analysis` 文件夹复制到项目的 Skill 目录：

```
<project>/.agent/skills/bili-content-analysis/
```

当用户请求涉及 B 站创作者追踪、字幕解读、时间线重建或内容深度分析时，Agent 将自动激活此 Skill。

## 👨‍💻 开发与测试

```bash
# 初始化
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv sync --dev

# 单元测试
uv run pytest -q

# 集成与性能基准（需凭据）
uv run python scripts/integration_suite.py -u <UID>
uv run python scripts/perf_baseline.py -u <UID> --tools dynamics -n 3
```

## 📦 发布 (维护者)

> **凭据**: 发布脚本优先使用 `UV_PUBLISH_TOKEN`；未设置时，会自动读取 `$HOME\.pypirc` 中对应的 `[pypi]` 或 `[testpypi]` Token。
> Twine 仅通过 `uvx` 临时执行包元数据校验，不作为项目依赖。

```powershell
# 构建 + 测试 + 包元数据校验（不上传）
.\scripts\pypi_release.ps1

# 上传到 TestPyPI
.\scripts\pypi_release.ps1 -TestPyPI -Upload

# 上传到 PyPI
.\scripts\pypi_release.ps1 -Upload
```

## Docker 部署

基于 `stdio` 传输，无外部端口暴露。

```bash
docker build -t bilistalker-mcp .
docker run -e SESSDATA=... bilistalker-mcp
```

## ⚠️ 常见问题

- **412 Precondition Failed**: 触发 B 站防爬虫机制。请刷新 `SESSDATA` 或确保已提供 `BUVID3`。
- **环境建议**: 云服务器 IP 极易被封锁，建议优先在本地环境运行。

## 开源协议

MIT

> **声明**：仅限个人研究与学习，禁止用于批量画像、骚扰或商业监测。

---
*本项目由 AI 辅助构建与维护。*
