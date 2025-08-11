# BiliStalkerMCP (b站用户视监MCP)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)
[![bilibili-api](https://img.shields.io/badge/Bilibili-API-ff69b4)](https://github.com/Nemo2011/bilibili-api)

**BiliStalkerMCP** 是一个基于 MCP (Model Context Protocol) 的服务，允许AI模型通过标准化协议获取指定Bilibili用户的最新视频和动态更新。

---

## 🚀 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/222wcnm/BiliStalkerMCP.git

# 进入项目目录
cd BiliStalkerMCP

# 使用 uv 以可编辑模式安装
uv pip install -e .
```

### 2. 配置环境变量

设置以下环境变量用于Bilibili API认证：

- `SESSDATA`: Bilibili账户的 `SESSDATA` cookie
- `BILI_JCT`: Bilibili账户的 `bili_jct` cookie  
- `BUVID3`: Bilibili账户的 `buvid3` cookie

> **如何获取Cookie?**
> 1. 登录 [bilibili.com](https://www.bilibili.com)
> 2. 打开浏览器开发者工具 (F12)
> 3. 切换到 `Application` -> `Cookies` -> `https://www.bilibili.com`
> 4. 复制 `SESSDATA`, `bili_jct`, 和 `buvid3` 的值

### 3. MCP客户端配置

```json
{
  "mcpServers": {
    "BiliStalkerMCP": {
      "command": "uv",
      "args": [
        "--directory",
        "<项目路径>",
        "run", 
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

> ⚠️ **安全提示**: 不要将包含凭证的配置文件提交到公共仓库

---

## ✨ 功能

- 🔍 用户视频获取：获取B站用户的最新视频列表
- 📱 动态更新监控：获取用户动态，按时间轴展示
- 🔗 智能用户匹配：支持用户名或用户ID双重查询
- 🎯 内容类型过滤：支持视频、文章等多种动态类型筛选
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
B站用户动态获取工具，支持多类型过滤，返回完整的动态内容和互动统计。

---

## 📁 资源支持

### 用户信息资源
- URI: `bili://user/{user_id}`
- 获取用户基本信息

### 用户视频资源
- URI: `bili://videos/{user_id}`
- 获取用户视频列表

### 用户动态资源
- URI: `bili://dynamics/{user_id}`
- 获取用户动态更新

### 数据结构Schema资源
- URI: `bili://schemas`
- 获取视频和动态的数据结构定义，帮助模型理解输出格式

### 资源访问示例
```python
# 通过URI直接访问资源（在支持资源的MCP客户端中）
read_resource("bili://user/123456")
read_resource("bili://videos/123456")
read_resource("bili://dynamics/123456")
```

---

## 📝 许可证

[MIT License](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE)
