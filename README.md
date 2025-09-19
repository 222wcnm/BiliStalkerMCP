# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.3-green)](https://pypi.org/project/bili-stalker-mcp/)

A Model Context Protocol (MCP) server for comprehensive Bilibili user data acquisition.

## Quick Start

### Installation
```bash
uvx bili-stalker-mcp
```

### Configuration
Add to your MCP client settings:

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

## Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_user_info` | User profile and stats | `user_id` or `username` |
| `get_user_video_updates` | Video publications with subtitles | `user_id`/`username`, `page`, `limit` |
| `get_user_dynamic_updates` | User dynamics with type filtering | `user_id`/`username`, `offset`, `limit`, `dynamic_type` |
| `get_user_articles` | Article publications | `user_id`/`username`, `page`, `limit` |
| `get_user_followings` | Following list | `user_id`/`username`, `page`, `limit` |

## Development

```bash
# Clone and setup
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .

# Run tests
python tests/test_suite.py -u <user_id_or_username>
```

## License

MIT