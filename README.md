# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)

Model Context Protocol server for Bilibili user data acquisition.

## Installation

```bash
uvx bili-stalker-mcp
```

## Configuration

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

## Tools

- `get_user_info` - User profile data
- `get_user_video_updates` - Video publications
- `get_user_dynamic_updates` - User dynamics
- `get_user_articles` - Article publications
- `get_user_followings` - Following list

## Development

```bash
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .
python tests/test_suite.py -u <user_id_or_username>
```

## License

MIT