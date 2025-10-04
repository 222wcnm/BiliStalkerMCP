#!/usr/bin/env python3
"""HTTP server startup script for Smithery.ai deployment."""

import os
import uvicorn
from fastmcp import FastMCP
from .server import create_server

if __name__ == "__main__":
    # Create the MCP server
    mcp_server: FastMCP = create_server()

    # Get port from environment variable set by Smithery (default to 8080)
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    # Run HTTP server using FastMCP's built-in method
    mcp_server.run(host=host, port=port, transport="http")
