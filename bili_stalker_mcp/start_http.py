#!/usr/bin/env python3
"""HTTP server startup script for Smithery.ai deployment."""

import os
import logging
from fastmcp import FastMCP
from .server import create_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Create the MCP server
    mcp_server: FastMCP = create_server()

    # Get port from environment variable set by Smithery (default to 8080)
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Starting HTTP server on {host}:{port}")

    # Let FastMCP handle the HTTP server with CORS enabled
    # This should automatically include CORS and health check functionality
    mcp_server.run(host=host, port=port, transport="http")
