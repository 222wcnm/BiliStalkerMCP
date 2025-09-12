# GEMINI.md - BiliStalkerMCP

## 1. Project Overview

BiliStalkerMCP is a Model Context Protocol (MCP) server designed to provide AI models with up-to-date information about Bilibili users. It allows AI agents to fetch a user's videos, dynamics, and articles in a structured format.

The project is built in Python and leverages `FastMCP` and `bilibili-api-python`.

After a major refactoring, the project is now fully asynchronous, uses caching for performance, and relies directly on the `bilibili-api` library for robust data parsing, having removed previous manual implementations.

### Exposed Tools:
*   `get_user_info`: Fetches a user's profile information.
*   `get_user_video_updates`: Retrieves a user's latest video uploads.
*   `get_user_dynamic_updates`: Gets a user's latest dynamics.
*   `get_user_articles`: Fetches a user's published articles.

---

## 2. Build, Run, and Test

### Installation
```bash
# Install and run the server via uvx
uvx bili-stalker-mcp
```

### Server Configuration (Example for Cline)
Add to `settings.json` and provide your Bilibili cookie values:
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

### Running Tests
1.  Create a `BILI_COOKIE.txt` file in the project root with your cookie string.
2.  Run the test suite:
    ```bash
    python tests/test_suite.py -u <username_or_uid>
    ```

---

## 3. Current Task: Data Payload Slimming

**Goal**: Modify the `fetch_*` functions in `bili_stalker_mcp/core.py` to return lean, structured JSON objects optimized for a downstream AI analysis agent.

### Target Data Schemas:

**`get_user_info` should return:**
```json
{
  "mid": 12345,
  "name": "UserName",
  "sign": "User's signature text.",
  "level": 6,
  "following": 500,
  "follower": 10000
}
```

**`get_user_video_updates` should return a list of:**
```json
{
  "bvid": "BV1xx411c7xx",
  "url": "https://www.bilibili.com/video/BV1xx411c7xx",
  "title": "Video Title",
  "description": "Video description text.",
  "created": "2023-10-27T10:00:00Z",
  "length": "10:30",
  "play": 150000
}
```

**`get_user_dynamic_updates` should return a list of:**
```json
{
  "dynamic_id": "123456789012345678",
  "type": "VIDEO" or "DRAW" or "FORWARD",
  "publish_time": "2023-10-27T10:00:00Z",
  "text": "The core text content of the dynamic.",
  "url": "URL to the dynamic or the content it refers to",
  "bvid": "BV1xx411c7xx", // (only if type is VIDEO)
  "stat": {
    "like": 100,
    "comment": 20,
    "forward": 5
  }
}
```

**`get_user_articles` should return a list of:**
```json
{
  "id": 12345,
  "url": "https://www.bilibili.com/read/cv12345",
  "title": "Article Title",
  "summary": "Article summary text.",
  "publish_time": "2023-10-27T10:00:00Z",
  "view": 5000,
  "like": 200,
  "comment": 30
}
```

### Next Step for New Agent:
1.  Read this document.
2.  Read `bili_stalker_mcp/core.py`.
3.  Start by modifying the `fetch_user_info` function to match the target schema above.