# BiliStalkerMCP

## Project Overview

BiliStalkerMCP is a Model Context Protocol (MCP) server designed for comprehensive Bilibili user data acquisition. It leverages the `bilibili-api-python` library to provide tools for fetching various user-related data from Bilibili, such as user profiles, video updates (including detailed subtitle information), dynamics, articles, and followings lists.

The project is structured as a standard Python package and exposes its functionality through a command-line interface (CLI) that starts the MCP server. It is configured using `pyproject.toml` and includes development dependencies for testing and code quality.

## Building and Running

This project uses `uv` for dependency management and running tasks.

### Dependencies

- **Main:** `bilibili-api-python`, `fastmcp`, `mcp[cli]`, `httpx`, `async-lru`
- **Development:** `pytest`, `pytest-cov`, `black`, `isort`, `flake8`, `mypy`

### Running the Server

The server can be started via the CLI entry point defined in `pyproject.toml`.

**Command:**
```bash
uvx bili-stalker-mcp
```

### Running Tests

The project includes a test suite. To run the tests:

```bash
# Make sure development dependencies are installed
uv pip install -e .[dev]

# Run the test suite
python tests/test_suite.py -u <user_id_or_username>
```

## Development Conventions

- **Code Style:** The project uses `black` for code formatting and `isort` for import sorting, with configurations defined in `pyproject.toml`.
- **Type Checking:** `mypy` is used for static type checking, with strict rules enforced.
- **Linting:** `flake8` is used for linting.
- **Entry Point:** The main application logic starts in `bili_stalker_mcp/cli.py`, which calls the `run` function from `bili_stalker_mcp/server.py`.
- **Core Logic:** The core data fetching logic is implemented in `bili_stalker_mcp/core.py`.
- **Configuration:** API endpoints and other constants are managed in `bili_stalker_mcp/config.py`.
