# GEMINI.md - BiliStalkerMCP

## 1. 项目概述

BiliStalkerMCP 是一个模型上下文协议 (MCP) 服务器，旨在为 AI 模型提供有关 Bilibili 用户的最新信息。它允许 AI 代理以结构化格式获取用户的视频、动态和文章。

该项目使用 Python 构建，并利用了 `FastMCP` 和 `bilibili-api-python`。

经过一次重大重构后，该项目现在是完全异步的，使用缓存来提高性能，并直接依赖 `bilibili-api` 库进行稳健的数据解析，移除了之前的手动实现。

### 暴露的工具:
*   `get_user_info`: 获取用户的个人资料信息。
*   `get_user_video_updates`: 检索用户的最新视频上传。
*   `get_user_dynamic_updates`: 获取用户的最新动态。
*   `get_user_articles`: 获取用户发布的文章。

---

## 2. 构建、运行与测试

### 安装
```bash
# 通过 uvx 安装并运行服务器
uvx bili-stalker-mcp
```

### 服务器配置 (Cline 示例)
添加到 `settings.json` 并提供您的 Bilibili cookie 值:
```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "YOUR_SESSDATA",
        "BILI_JCT": "YOUR_BILI_JCT",
        "BUVID3": "YOUR_BUVID3"
      }
    }
  }
}
```

### 运行测试
1.  在项目根目录中创建一个 `BILI_COOKIE.txt` 文件，并包含您的 cookie 字符串。
2.  运行测试套件:
    ```bash
    python tests/test_suite.py -u <username_or_uid>
    ```

---

## 3. 当前任务：定义数据负载

**目标**: 修改 `bili_stalker_mcp/core.py` 中的 `fetch_*` 函数，使其根据以下要求返回特定的结构化 JSON 对象。

### 目标数据模式:

**`get_user_info` 应返回:**
返回 `user.get_user_info` 和 `relation.stat` 中的所有字段，但**排除** `vip` (会员) 和 `official` (认证) 相关字段。
```json
{
  "mid": 12345,
  "name": "UserName",
  "face": "http://...",
  "sign": "用户的个性签名。",
  "level": 6,
  "birthday": "MM-DD",
  "sex": "男",
  "top_photo": "http://...",
  "live_room": {
      "roomid": 12345,
      "url": "http://...",
      "title": "直播间标题",
      "liveStatus": 1
  },
  "following": 500,
  "follower": 10000
}
```

**`get_user_video_updates` 应返回一个列表，其中包含:**
返回视频的所有可用字段。如果视频没有字幕，`subtitle` 字段应包含字符串 "视频无字幕"。
```json
{
  "bvid": "BV1xx411c7xx",
  "aid": 54321,
  "title": "视频标题",
  "description": "视频简介文本。",
  "created": 1672531200,
  "length": "10:30",
  "play": 150000,
  "comment": 1200,
  "favorites": 3000,
  "like": 8000,
  "pic": "http://...",
  "subtitle": "视频无字幕"
}
```

**`get_user_dynamic_updates` 应返回一个列表，其中包含:**
(需求待定，暂时不做修改。)
```json
{
  "dynamic_id": "123456789012345678",
  "type": "VIDEO / DRAW / FORWARD",
  "publish_time": "2023-10-27T10:00:00Z",
  "text": "动态的核心文本内容。",
  "url": "指向动态或其引用内容URL",
  "bvid": "BV1xx411c7xx", // (仅当类型为 VIDEO 时)
  "stat": {
    "like": 100,
    "comment": 20,
    "forward": 5
  }
}
```

**`get_user_articles` 应返回一个列表，其中包含:**
返回所有可用字段，但**排除** `category.name`。
```json
{
  "id": 12345,
  "title": "文章标题",
  "summary": "文章摘要文本。",
  "banner_url": "http://...",
  "publish_time": 1672531200,
  "stats": {
    "view": 5000,
    "like": 200,
    "reply": 30
  },
  "words": 1500
}
```

### 后续步骤:
1.  阅读此文档以确认需求。
2.  阅读 `bili_stalker_mcp/core.py`。
3.  根据上述模式修改 `fetch_*` 函数，从 `fetch_user_info` 开始。
4.  频繁提交变更。
