# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.5-green)](https://pypi.org/project/bili-stalker-mcp/)
[![smithery badge](https://smithery.ai/badge/@222wcnm/bilistalkermcp)](https://smithery.ai/server/@222wcnm/bilistalkermcp)

BiliStalkerMCP is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for Bilibili, specifically designed for AI assistants (like Claude, ChatGPT).

**English | [中文说明](README_zh.md)**

### Installation

#### Installing via Smithery

To install bilistalkermcp automatically via [Smithery](https://smithery.ai/server/@222wcnm/bilistalkermcp):

```bash
npx -y @smithery/cli install @222wcnm/bilistalkermcp
```

#### Manual Installation
```bash
uvx bili-stalker-mcp
```

### Configuration

Add to your MCP client settings (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "your_sessdata",
        "BILI_JCT": "your_bili_jct",
        "BUVID3": "your_buvid3"
      }
    }
  }
}
```

> **Tip**: You can find these values in your browser by pressing F12 -> Application -> Cookies on the Bilibili website.

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `SESSDATA` | **Yes** | Authentication token from Bilibili cookies. |
| `BILI_JCT` | No | CSRF token from cookies. |
| `BUVID3` | No | Browser fingerprint, helps reduce rate limiting issues. |
| `BILI_LOG_LEVEL` | No | Log level (`INFO`, `DEBUG`, `WARNING`), default is `WARNING`. |

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_user_info` | User profile and stats | `user_id` or `username` |
| `get_user_video_updates` | Video publications with subtitles | `user_id`/`username`, `page`, `limit` |
| `get_user_dynamic_updates` | User dynamics with type filtering | `user_id`/`username`, `offset`, `limit`, `dynamic_type` |
| `get_user_articles` | Article publications | `user_id`/`username`, `page`, `limit` |
| `get_user_followings` | Following list | `user_id`/`username`, `page`, `limit` |

### Dynamic Type Filtering

The `get_user_dynamic_updates` tool supports filtering by type:

| `dynamic_type` | Description |
|----------------|-------------|
| `ALL` (default) | TEXT, IMAGE_TEXT, REPOST only (analysis-focused) |
| `ALL_RAW` | All types including VIDEO, ARTICLE |
| `VIDEO` | Video dynamics only |
| `ARTICLE` | Article dynamics only |
| `DRAW` | Image-text dynamics only |
| `TEXT` | Text-only dynamics |

## Development

```bash
# Clone and setup
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .

# Run tests
python tests/test_suite.py -u <user_id_or_username>
```

## 🐳 Docker Support

You can also run the server using Docker:

```bash
docker build -t bilistalker-mcp .
docker run -e SESSDATA=... -e BILI_JCT=... -e BUVID3=... bilistalker-mcp
```

## ❓ Troubleshooting

**Q: Why am I getting "412 Precondition Failed"?**
A: This usually means you are being rate-limited or blocked by Bilibili. Try to:
1. Refresh your `SESSDATA`.
2. Ensure you provide `BUVID3`.
3. If running on a cloud server, try running locally as cloud IPs are more likely to be blocked.

## License

MIT

---

*This project is built and maintained with the help of AI.*

