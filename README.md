# BiliStalkerMCP (哔站用户视监MCP)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)

一个用于获取B站用户视频和动态更新的MCP服务器。

## 快速开始

**1. 安装服务:**
```bash
uvx bili-stalker-mcp
```

**2. 配置客户端 (例如 Cline):**
将以下内容添加到 `settings.json`:
```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "你的SESSDATA",
        "BILI_JCT": "你的BILI_JCT",
        "BUVID3": "你的BUVID3"
      }
    }
  }
}
```
> **提示**: Cookie 可在登录 bilibili.com 后，通过浏览器开发者工具 (F12) 的 `Application > Cookies` 中找到。

## API

### 工具

- **`get_user_video_updates(user_id: int, username: str, limit: int = 10)`**
  获取用户的最新视频列表。

- **`get_user_dynamic_updates(user_id: int, username: str, limit: int = 10, dynamic_type: str = "ALL")`**
  获取用户的最新动态列表。

### 格式化提示 (可选)

- **`format_video_response(videos: str)`**
  用于处理 `get_user_video_updates` 返回的视频数据。

- **`format_dynamic_response(dynamics: str)`**
  用于处理 `get_user_dynamic_updates` 返回的动态数据。

## 许可证

[MIT](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE)
