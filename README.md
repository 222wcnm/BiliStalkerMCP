# BiliStalkerMCP (哔站用户视监MCP)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)

BiliStalkerMCP 是一个模型上下文协议 (MCP) 服务器，旨在为 AI 模型提供关于特定B站用户的深度、实时且只读的各类信息。

## 核心原则

- **用户中心**: 严格专注于获取单个用户的详细数据画像。
- **只读操作**: 所有工具只检索信息，不进行任何点赞、评论、发布等修改性操作。
- **数据时效**: 致力于提供新鲜、准确的数据。

## 快速开始

**1. 安装服务器:**
```powershell
uvx bili-stalker-mcp
```

**2. 配置您的MCP客户端 (例如 Gemini CLI):**
将以下配置添加到您客户端的设置文件 (例如 `settings.json`) 中：
```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "此处填写你的SESSDATA",
        "BILI_JCT": "此处填写你的BILI_JCT",
        "BUVID3": "此处填写你的BUVID3"
      }
    }
  }
}
```
> **提示**: 登录 bilibili.com 后，您可以在浏览器的开发者工具 (F12) 的 `Application > Cookies` 选项中找到您的 Cookie 值。

## 核心工具

本服务器为 AI 模型提供以下核心工具：

- **`get_user_info`**: 获取用户的详细个人资料，包括昵称、签名、等级和粉丝统计。
- **`get_user_video_updates`**: 获取用户最近发布的视频列表，包含标题、统计数据和封面图。
- **`get_user_dynamic_updates`**: 获取用户最近的动态（帖子），支持纯文字、视频和图文等多种类型。
- **`get_user_articles`**: 获取用户最近发布的专栏文章列表，包含摘要、统计数据和横幅。

## 本地测试

如需运行测试套件，请先在项目根目录创建一个 `BILI_COOKIE.txt` 文件，并将您的完整 Cookie 字符串粘贴进去。然后，运行以下命令：

```powershell
python tests/test_suite.py -u <目标用户的昵称或UID>
```

## 许可证

[MIT](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE)