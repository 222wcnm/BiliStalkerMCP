#!/usr/bin/env python3
"""HTTP server using direct implementation for Smithery.ai deployment."""

import os
import logging
from fastmcp import FastMCP
from .server_direct import create_server_direct

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # Create the MCP server with direct HTTP implementation
    mcp_server: FastMCP = create_server_direct()

    # Get port from environment variable set by Smithery (default to 8080)
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"Starting HTTP server with direct implementation on {host}:{port}")

    # Let FastMCP handle the HTTP server with CORS enabled
    # This should automatically include CORS and health check functionality
    mcp_server.run(host=host, port=port, transport="http")
