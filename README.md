# BiliStalkerMCP (b站用户视监MCP)

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)&nbsp;
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP-orange)](https://github.com/jlowin/fastmcp)&nbsp;
[![bilibili-api](https://img.shields.io/badge/Bilibili-API-ff69b4)](https://github.com/Nemo2011/bilibili-api)

**BiliStalkerMCP** 是一个 [MCP (Model-Context-Protocol)](https://github.com/model-context-protocol) 服务，允许AI模型通过“工具调用”（基于MCP协议）获取指定Bilibili用户的最新视频动态。

---

## 🚀 快速开始

### 1. 安装

推荐通过克隆仓库后进行本地安装，这能确保您使用的是最新版本。

```bash
# 克隆仓库
git clone https://github.com/222wcnm/BiliStalkerMCP.git

# 进入项目目录
cd BiliStalkerMCP

# 使用 uv 以可编辑模式安装
uv pip install -e .
```

### 2. 配置环境变量

为了验证Bilibili API请求，需要提供自己的凭证信息。请在运行环境中设置以下环境变量：

- `SESSDATA`: 您的Bilibili账户的 `SESSDATA` cookie。
- `BILI_JCT`: 您的Bilibili账户的 `bili_jct` cookie。
- `BUVID3`: 您的Bilibili账户的 `buvid3` cookie。

> **如何获取Cookie?**
> 1. 登录 [bilibili.com](https://www.bilibili.com)。
> 2. 打开浏览器开发者工具 (通常按 `F12`)。
> 3. 切换到 `Application` -> `Cookies` -> `https://www.bilibili.com`。
> 4. 找到并复制 `SESSDATA`, `bili_jct`, 和 `buvid3` 的值。

### 3. MCP客户端配置

在您的MCP客户端中，添加以下服务器配置：

```json
{
  "mcpServers": {
    "BiliStalkerMCP": {
      "command": "uv",
      "args": [
        "--directory",
        "<YOUR_PROJECT_PATH>",
        "run",
        "bili-stalker-mcp"
      ],
      "env": {
        "SESSDATA": "在此处填入您的SESSDATA",
        "BILI_JCT": "在此处填入您的BILI_JCT",
        "BUVID3": "在此处填入您的BUVID3"
      }
    }
  }
}
```

> ⚠️ **安全提示**  
> 请勿将包含个人凭证的配置文件提交到任何公共代码仓库。

---

## ✨ 功能

- **获取用户视频更新**: 通过 `user_id` 或 `username` 查询指定B站UP主的最新视频列表。
- **详细信息**: 返回包括用户信息（昵称、头像、签名等）和视频信息（标题、封面、播放量、BVID、URL等）。
- **智能搜索**: 当提供 `username` 时，会自动搜索并匹配最相关的用户。

---

## 🛠️ 工具详情

### `get_user_video_updates`

获取指定B站用户的最新视频更新信息。

#### 参数

- `user_id` (int, 可选): B站用户的唯一ID。
- `username` (str, 可选): B站用户的昵称。
  - 必须至少提供一个参数。
  - **如果同时提供，`user_id` 优先。**
- `limit` (int, 可选): 获取的视频数量限制，默认为 `10`，最大为 `50`。

#### 返回示例

返回值为一个包含用户和视频信息的 **JSON 对象**：

```json
{
  "user": {
    "mid": 123456,
    "name": "示例用户",
    "face": "https://i1.hdslb.com/bfs/face/xxxxxxxx.jpg",
    "sign": "这是一个签名",
    "level": 6
  },
  "videos": [
    {
      "bvid": "BV1xx411c7xX",
      "aid": 987654321,
      "title": "示例视频标题",
      "description": "这是一个示例视频描述。",
      "created": 1678886400,
      "length": "10:30",
      "pic": "http://i2.hdslb.com/bfs/archive/xxxxxxxx.jpg",
      "play": 100000,
      "favorites": 5000,
      "author": "示例用户",
      "mid": 123456,
      "url": "https://www.bilibili.com/video/BV1xx411c7xX"
    }
  ],
  "total": 100
}
```

> **说明**: `total` 字段表示该用户总共发布的视频数量。

---

## 🔗 相关项目

- [lesir831/bilibili-video-info-mcp](https://github.com/lesir831/bilibili-video-info-mcp): 用于获取B站视频信息的另一个MCP服务。
- [huccihuang/bilibili-mcp-server](https://github.com/huccihuang/bilibili-mcp-server): 功能更全面的Bilibili MCP服务。

---

## 📝 许可证

本项目基于 [MIT License](https://github.com/222wcnm/BiliStalkerMCP/blob/main/LICENSE) 开源。

---

> **AI生成声明**  
> 本项目的代码和文档在开发过程中部分使用了AI辅助工具生成。
