# GEMINI.md - BiliStalkerMCP

## Project Overview

BiliStalkerMCP is a Model Context Protocol (MCP) server designed to provide AI models with up-to-date information about Bilibili users. It allows AI agents to fetch a user's videos, dynamics (social media-style posts), and articles in a structured format.

The project is built in Python and leverages the following key technologies:

*   **FastMCP**: A Python framework for rapidly building MCP servers.
*   **bilibili-api-python**: A comprehensive library for interacting with the Bilibili API.
*   **WBI Signing**: Implements the necessary signing mechanism to access some of Bilibili's newer APIs.

The server exposes several tools that an AI agent can call:

*   `get_user_info`: Fetches a user's profile information.
*   `get_user_video_updates`: Retrieves a user's latest video uploads.
*   `get_user_dynamic_updates`: Gets a user's latest dynamics, with support for filtering by type (e.g., video, article, image posts).
*   `get_user_articles`: Fetches a user's published articles.

It also includes prompts to format the raw JSON output from the tools into human-readable Markdown.

## Building and Running

### Installation

The project is packaged and can be installed using a Python package manager like `uv` or `pip`.

```bash
# Using uv
uvx bili-stalker-mcp

# Or using pip
pip install bili-stalker-mcp
```

### Running the Server

The server is designed to be run as a command-line application. The `pyproject.toml` file defines the entry point.

To run the server for a client like Cline, you would configure it in the client's settings file, specifying the command and necessary environment variables for Bilibili authentication (SESSDATA, BILI_JCT, BUVID3).

Example `settings.json` for Cline:
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

The project includes a test suite in `tests/test_suite.py`. It can be run from the command line to verify the core functionality.

1.  **Set up credentials**: Create a `BILI_COOKIE.txt` file in the project root with your Bilibili cookie string, or set the `SESSDATA`, `BILI_JCT`, and `BUVID3` environment variables.
2.  **Run the test suite**:

    ```bash
    python tests/test_suite.py -u <username_or_uid> -l <limit>
    ```

## Development Conventions

The `.clinerules/bili-stalker-mcp-guidelines.md` file outlines the development philosophy for this project. Key conventions include:

*   **User-Focused**: The project is strictly focused on fetching data for a *specific* Bilibili user.
*   **Read-Only**: All operations must be read-only. No liking, commenting, or other state-changing actions are allowed.
*   **Data Freshness**: The server should provide the most up-to-date information possible.
*   **Custom Parsing**: The project includes custom parsers in `bili_stalker_mcp/parsers.py` to handle complex data structures from the Bilibili API, especially for "draw" dynamics (image posts), which the underlying `bilibili-api-python` library may not fully parse. Any changes to dynamic fetching logic must be carefully tested against this.
*   **Code Style**: The project uses `black` for code formatting and `isort` for import sorting, with configurations defined in `pyproject.toml`.
