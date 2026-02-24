# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.7.0-green)](https://pypi.org/project/bili-stalker-mcp/)

BiliStalkerMCP 是基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 的 Bilibili 数据接入服务，专为 AI 助手（如 Claude, ChatGPT）设计，提供精准、深度的用户行为分析支持。

**[English](README.md) | 中文说明**

## 🚀 快速开始

### 安装

```bash
uvx bili-stalker-mcp
# 或
pip install bili-stalker-mcp
```

### 配置 (Claude Desktop)

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "必填_SESSDATA",
        "BILI_JCT": "可选_BILI_JCT",
        "BUVID3": "可选_BUVID3"
      }
    }
  }
}
```

> **凭据获取**: 在 B 站网页端按下 F12 -> Application -> Cookies 中获取相关值。

### 环境变量

| 变量名 | 必填 | 描述 |
|--------|:----:|------|
| `SESSDATA` | **是** | B 站登录凭证。 |
| `BILI_JCT` | 否 | CSRF Token，涉及高权限操作时必需。 |
| `BUVID3` | 否 | 硬件指纹，显著降低风控阻断风险。 |
| `BILI_LOG_LEVEL` | 否 | 映射至 `DEBUG`, `INFO` (默认), `WARNING`。 |

## 🛠️ 工具集

| 工具 | 功能描述 | 参数 |
|------|----------|------|
| `get_user_info` | 档案资料与核心统计数据 | `user_id_or_username` |
| `get_user_video_updates` | 视频投稿列表与字幕摘要 | `user_id_or_username`, `page`, `limit` |
| `get_user_dynamic_updates` | 基于 Cursor 游标的动态流，支持多级过滤 | `user_id_or_username`, `cursor`, `limit`, `dynamic_type` |
| `get_user_articles` | 专栏文章深度获取 | `user_id_or_username`, `page`, `limit` |
| `get_user_followings` | 用户关注列表分析 | `user_id_or_username`, `page`, `limit` |

### 动态类型过滤 (`dynamic_type`)

- `ALL` (默认): 仅文本、图文、转发（最适合 AI 分析）。
- `ALL_RAW`: 原始全量数据（包含视频及专栏）。
- `VIDEO`, `ARTICLE`, `DRAW`, `TEXT`: 特定分类过滤。

**分页机制**: 响应包含 `next_cursor`。后续请求传入此参数可实现连续拉取。

## 👨‍💻 开发与测试

```bash
# 初始化
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .[dev]

# 单元测试
uv run pytest -q

# 集成与性能基准（需凭据）
uv run python scripts/integration_suite.py -u <UID>
uv run python scripts/perf_baseline.py -u <UID> --tools dynamics -n 3
```

## 📦 发布 (维护者)

> **前置要求**: 请确保系统用户目录下已配置 `.pypirc` 文件以提供 PyPI 凭证。

```powershell
# 构建 + 测试 + twine 检查（不上传）
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

---
*本项目由 AI 辅助构建与维护。*