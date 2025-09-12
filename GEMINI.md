# GEMINI.md - BiliStalkerMCP

## 1. 项目概述

BiliStalkerMCP 是一个模型上下文协议 (MCP) 服务器，旨在为 AI 模型提供关于特定 Bilibili 用户的深度、实时且只读的各类信息。

该项目使用 Python 构建，并利用了 `FastMCP` 和 `bilibili-api-python`。项目代码完全异步，并使用缓存以提高性能。

### 核心原则
- **用户中心**: 严格专注于获取单个用户的详细数据画像，不实现平台级搜索或发现功能。
- **只读操作**: 所有工具只检索信息，不进行任何点赞、评论、发布等修改性操作。
- **数据时效**: 致力于提供新鲜、准确的数据。

### 暴露的工具与提示

#### 工具 (Tools)
- **`get_user_info`**: 获取用户的详细个人资料，包括昵称、签名、等级和粉丝统计。
- **`get_user_video_updates`**: 获取用户最近发布的视频列表，包含标题、统计数据和封面图。
- **`get_user_dynamic_updates`**: 获取用户最近的动态（帖子），支持纯文字、视频和图文等多种类型。
- **`get_user_articles`**: 获取用户最近发布的专栏文章列表，包含摘要、统计数据和横幅。

#### 提示 (Prompts)
- **`format_user_info_response`**: 将用户信息格式化为易读的Markdown。
- **`format_video_response`**: 将视频列表格式化为易读的Markdown。
- **`format_dynamic_response`**: 将动态列表格式化为易读的Markdown。
- **`format_articles_response`**: 将文章列表格式化为易读的Markdown。

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

## 3. 开发准则与注意事项

### 3.1. 核心开发准则
- **前置知识**: 在实施任何功能前，必须对Model Context Protocol (MCP)、FastMCP框架及Bilibili API有充分理解。
- **信息获取**: 鼓励使用外部信息工具来补充背景知识。
- **CLI语法**: 优先使用PowerShell语法。

### 3.2. 图文动态解析
- **问题背景**: 项目早期曾遇到 `bilibili-api-python` 无法直接从图文动态中返回完整文本内容的问题。
- **解决方案**: 通过 `core.py` 中的自定义解析逻辑 (`_parse_dynamic_item`)，对原始 API 返回的动态数据进行深度解析，提取并重组图文内容。
- **开发要求**: 任何涉及动态数据获取或处理的修改，都必须进行回归测试，确保图文动态的文本内容能够被正确、完整地提取。