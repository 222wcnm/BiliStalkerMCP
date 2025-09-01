# BiliStalkerMCP (b站用户视监MCP)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/bili_stalker_mcp.svg)](https://pypi.org/project/bili_stalker_mcp/)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)
[![bilibili-api](https://img.shields.io/badge/Bilibili-API-ff69b4)](https://github.com/Nemo2011/bilibili-api)

**BiliStalkerMCP** 是一个基于 MCP (Model Context Protocol) 的服务，允许AI模型通过标准化协议获取指定Bilibili用户的最新视频和动态更新。

---

## 🚀 快速开始

### 1. 安装

通过 `uvx` 或 `pipx`，你可以轻松地在任何地方运行 `bili-stalker-mcp`，而无需担心项目路径或虚拟环境。

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

> **如何获取Cookie?**
> 1. 登录 [bilibili.com](https://www.bilibili.com)
> 2. 打开浏览器开发者工具 (F12)
> 3. 切换到 `Application` -> `Cookies` -> `https://www.bilibili.com`
> 4. 复制 `SESSDATA`, `bili_jct`, 和 `buvid3` 的值

> ⚠️ **安全提示**: 不要将包含凭证的配置文件提交到公共仓库

---

## ✨ 功能

- 🔍 用户视频获取：获取B站用户的最新视频列表
- 📱 动态更新监控：获取用户动态，按时间轴展示
- 🔗 智能用户匹配：支持用户名或用户ID双重查询
- 📊 数据结构规范：提供标准化JSON输出格式

---

## 💬 提示预设

- **`format_video_response`**: 视频数据规范化展示，包含播放量排序
- **`format_dynamic_response`**: 动态全类型时间轴显示
- **`analyze_user_activity`**: 多维度用户创作活跃度分析

---

## 🛠️ 工具

### `get_user_video_updates`
B站用户视频列表查询工具，支持用户名自动搜索，返回完整的视频统计信息。

### `get_user_dynamic_updates`
B站用户动态获取工具，返回完整的动态内容和互动统计。

---

## 📁 资源支持

### 用户信息资源
- URI: `bili://user/{user_id}/info`
- 获取用户基本信息

### 用户视频资源
- URI: `bili://user/{user_id}/videos`
- 获取用户视频列表

### 用户动态资源
- URI: `bili://user/{user_id}/dynamics`
- 获取用户动态更新

### 数据结构Schema资源
- URI: `bili://schemas`
- 获取视频和动态的数据结构定义，帮助模型理解输出格式

### 资源访问示例
```python
# 通过URI直接访问资源（在支持资源的MCP客户端中）
read_resource("bili://user/123456/info")
read_resource("bili://user/123456/videos")
read_resource("bili://user/123456/dynamics")
```

---

## 📝 许可证

[MIT License](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE)
