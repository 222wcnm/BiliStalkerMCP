# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)

基于MCP协议的B站用户数据获取服务，支持视频和动态信息查询。

## 安装与配置

### 1. 安装

```bash
uvx bili-stalker-mcp
```

### 2. MCP客户端配置

将以下配置添加到你的MCP客户端（如Cline）的 `settings.json` 文件中：

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": [
        "bili-stalker-mcp"
      ],
      "env": {
        "SESSDATA": "您的SESSDATA",
        "BILI_JCT": "您的BILI_JCT",
        "BUVID3": "您的BUVID3"
      }
    }
  }
}
```

**获取Cookie**：登录bilibili.com → F12 → Application → Cookies → 复制所需值

## 功能特性

- 🔍 获取用户视频列表（播放量、时长、发布日期）
- 📱 获取用户动态（支持类型过滤）
- 🔗 支持用户名或ID查询
- 📊 标准化JSON输出
- 🔄 内置重试机制
- 🎨 Markdown格式化预设

## 工具与资源

### 工具
- `get_user_video_updates` - 获取用户视频
  - 参数：`user_id`/`username`（必填其一），`limit`（默认10）
  
- `get_user_dynamic_updates` - 获取用户动态
  - 参数：`user_id`/`username`（必填其一），`limit`（默认10），`dynamic_type`（默认ALL）

### 提示预设
- `format_video_response` - 视频数据Markdown格式化
- `format_dynamic_response` - 动态数据时间轴格式化

### 资源
- `bili://schemas` - 数据结构定义

## 许可证

[MIT License](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE)
