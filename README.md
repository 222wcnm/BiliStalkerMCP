# BiliStalkerMCP

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-orange)](https://github.com/jlowin/fastmcp)
[![Version](https://img.shields.io/badge/Version-2.7.0-green)](https://pypi.org/project/bili-stalker-mcp/)

BiliStalkerMCP is an [MCP](https://modelcontextprotocol.io) server providing high-fidelity Bilibili data access for AI agents (Claude, ChatGPT).

**English | [中文说明](README_zh.md)**

### Installation

```bash
uvx bili-stalker-mcp
# or
pip install bili-stalker-mcp
```

### Configuration (Claude Desktop)

```json
{
  "mcpServers": {
    "bilistalker": {
      "command": "uvx",
      "args": ["bili-stalker-mcp"],
      "env": {
        "SESSDATA": "required_sessdata",
        "BILI_JCT": "optional_jct",
        "BUVID3": "optional_buvid3"
      }
    }
  }
}
```

> **Auth**: Obtain `SESSDATA` from Browser DevTools (F12) > Application > Cookies > `.bilibili.com`.

### Environment Variables

| Key | Req | Description |
|-----|:---:|-------------|
| `SESSDATA` | **Yes** | Bilibili session token. |
| `BILI_JCT` | No | CSRF protection token. |
| `BUVID3` | No | Hardware fingerprint (reduces rate-limiting risk). |
| `BILI_LOG_LEVEL` | No | `DEBUG`, `INFO` (Default), `WARNING`. |

## Available Tools

| Tool | Capability | Parameters |
|------|------------|------------|
| `get_user_info` | Profile & core statistics | `user_id_or_username` |
| `get_user_video_updates` | Video uploads with subtitle analysis | `user_id_or_username`, `page`, `limit` |
| `get_user_dynamic_updates` | Dynamics with cursor pagination & filtering | `user_id_or_username`, `cursor`, `limit`, `dynamic_type` |
| `get_user_articles` | Long-form article retrieval | `user_id_or_username`, `page`, `limit` |
| `get_user_followings` | Subscription list analysis | `user_id_or_username`, `page`, `limit` |

### Dynamic Filtering (`dynamic_type`)

- `ALL` (default): Text, Image-Text, and Reposts.
- `ALL_RAW`: Unfiltered (includes Videos & Articles).
- `VIDEO`, `ARTICLE`, `DRAW`, `TEXT`: Specific category filtering.

**Pagination**: Responses include `next_cursor`. Pass this to subsequent requests for seamless scrolling.

## Development

```bash
# Setup
git clone https://github.com/222wcnm/BiliStalkerMCP.git
cd BiliStalkerMCP
uv pip install -e .[dev]

# Test
uv run pytest -q

# Integration & Performance (Requires Auth)
uv run python scripts/integration_suite.py -u <UID>
uv run python scripts/perf_baseline.py -u <UID> --tools dynamics -n 3
```

## Release (Maintainers)

> **Prerequisite**: Ensure that a `.pypirc` file is configured in your user home directory to provide PyPI credentials.

```powershell
# Build + test + twine check (no upload)
.\scripts\pypi_release.ps1

# Upload to TestPyPI
.\scripts\pypi_release.ps1 -TestPyPI -Upload

# Upload to PyPI
.\scripts\pypi_release.ps1 -Upload
```

## Docker

Runs via `stdio` transport. No ports exposed.

```bash
docker build -t bilistalker-mcp .
docker run -e SESSDATA=... bilistalker-mcp
```

## Troubleshooting

- **412 Precondition Failed**: Bilibili anti-crawling system triggered. Refresh `SESSDATA` or provide `BUVID3`.
- **Cloud IPs**: Highly susceptible to blocking; local execution is recommended.

## License

MIT

---
*This project is built and maintained with the help of AI.*
