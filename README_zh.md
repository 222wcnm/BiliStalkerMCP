# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.5-green)](https://pypi.org/project/bili-stalker-mcp/)
[![smithery badge](https://smithery.ai/badge/@222wcnm/bilistalkermcp)](https://smithery.ai/server/@222wcnm/bilistalkermcp)

BiliStalkerMCP 是一个基于 Model Context Protocol (MCP) 的 Bilibili 数据获取服务，专为 AI 助理（如 Claude, ChatGPT）设计，能够帮助 AI 深度获取和分析 B 站用户数据。

**[English](README.md) | 中文说明**

## 🌟 核心特性

- **最强反爬机制**: 内置 `curl_cffi` 模拟浏览器指纹 + 自动 `Buvid` 生成，极大程度降低 412 拦截概率。
- **丰富的工具集**: 支持获取用户信息、视频动态、图文动态、专栏文章及关注列表。
- **AI 友好数据**: 渲染可直接用的图片链接、可读的时间戳格式，以及详细的字幕摘要。
- **自动重试**: 智能指数退避重试机制，自动处理网络抖动和临时限流。

## 🚀 快速开始

### 安装

#### 方式 A: 通过 Smithery 自动安装 (推荐)

如果你使用 [Smithery](https://smithery.ai/server/@222wcnm/bilistalkermcp):

```bash
npx -y @smithery/cli install @222wcnm/bilistalkermcp
```

#### 方式 B: 手动安装

```bash
uv pip install bili-stalker-mcp
```

### 配置

在您的 MCP 客户端（如 Claude Desktop）配置文件中添加以下内容：

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "你的_SESSDATA",
        "BILI_JCT": "你的_BILI_JCT",
        "BUVID3": "你的_BUVID3"
      }
    }
  }
}
```

> **提示**: 您可以在 B 站网页端按下 F12 -> Application -> Cookies 中找到这些值。

## 🛠️ 可用工具

| 工具名称 | 描述 | 参数 |
|------|-------------|------------|
| `get_user_info` | 获取用户资料及统计数据 | `user_id_or_username` |
| `get_user_video_updates` | 获取最新发布的视频（含字幕汇总） | `user_id_or_username`, `page`, `limit` |
| `get_user_dynamic_updates` | 获取用户动态（支持分类过滤） | `user_id_or_username`, `offset`, `limit`, `dynamic_type` |
| `get_user_articles` | 获取专栏文章列表 | `user_id_or_username`, `page`, `limit` |
| `get_user_followings` | 获取用户关注列表 | `user_id_or_username`, `page`, `limit` |

### 动态类型过滤 (`dynamic_type`)

`get_user_dynamic_updates` 支持以下过滤模式：

- `ALL` (默认): 仅文本/图文/转发（最适合 AI 分析）
- `ALL_RAW`: 包含视频和专栏在内的所有类型
- `VIDEO`: 仅视频投稿动态
- `ARTICLE`: 仅专栏投稿动态
- `DRAW`: 仅带图片的图文动态
- `TEXT`: 仅纯文字动态

## 📊 数据返回特色

- **人性化时间**: 所有时间字段除原始时间戳外，均提供格式化后的 `created_time` 或 `publish_time`。
- **图片预览**: 视频封面 (`pic`) 和动态图片 (`images`) 采用 Markdown 友好的 URL 格式。
- **字幕分析**: 自动检测视频是否有字幕，并提供 `subtitle_summary`（如“有2种字幕: 中文(AI生成), 英文”）。
- **转发回溯**: `REPOST` 类型的动态会自动包含 `origin` 对象，展示被转发内容的完整详情。

## 👨‍💻 开发与测试

```bash
# 克隆并安装开发版本
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .[dev]

# 运行全功能测试套件
uv run tests/test_suite.py -u <UID或用户名>
```

## 📄 开源协议

MIT

---

*本项目完全由 AI (Antigravity) 构建并维护，旨在探索 AI 与 MCP 标准的无限可能。*
