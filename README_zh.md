# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.5-green)](https://pypi.org/project/bili-stalker-mcp/)
[![smithery badge](https://smithery.ai/badge/@222wcnm/bilistalkermcp)](https://smithery.ai/server/@222wcnm/bilistalkermcp)

BiliStalkerMCP 是一个基于 Model Context Protocol (MCP) 的 Bilibili 数据获取服务，专为 AI 助理（如 Claude, ChatGPT）设计，能够帮助 AI 深度获取和分析 B 站用户数据。


**[English](README.md) | 中文说明**

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

### 环境变量说明

| 变量名 | 必填 | 描述 |
|--------|:----:|------|
| `SESSDATA` | **是** | B 站登录凭证，获取大多数数据的基础。 |
| `BILI_JCT` | 否 | CSRF Token，若涉及更高权限操作可能需要。 |
| `BUVID3` | 否 | 浏览器指纹，有助于进一步降低风控风险。 |
| `BILI_LOG_LEVEL` | 否 | 日志等级 (`INFO`, `DEBUG`, `WARNING`)，默认 `WARNING`。 |

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

## 👨‍💻 开发与测试

```bash
# 克隆并安装开发版本
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .[dev]

# 运行全功能测试套件
uv run tests/test_suite.py -u <UID或用户名>
```

## 🐳 Docker 支持

如果您更喜欢使用容器，可以使用提供的 `Dockerfile`:

```bash
docker build -t bilistalker-mcp .
docker run -e SESSDATA=... -e BILI_JCT=... -e BUVID3=... bilistalker-mcp
```

## ❓ 常见问题

**Q: 为什么我遇到了 412 错误？**
A: 412 错误通常表示 B 站触发了风控。请确保：
1. `SESSDATA` 是最新的且未失效。
2. 尽可能提供 `BUVID3`。
3. 如果是在云服务器上运行，请尝试在本地运行，因为云服务的 IP 段更容易被拦截。

**Q: 我需要所有三个 Cookie 吗？**
A: 只要有 `SESSDATA` 就可以运行，但强烈建议同时提供 `BILI_JCT` 和 `BUVID3` 以确保最高稳定性。

## 📄 开源协议

MIT

---

*本项目由 AI 辅助构建与维护。*
