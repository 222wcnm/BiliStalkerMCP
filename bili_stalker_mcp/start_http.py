#!/usr/bin/env python3
"""HTTP server startup script for Smithery.ai deployment."""

import os
import logging
from fastmcp import FastMCP
from .server import create_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom HTTP server with proper configuration for Smithery
class SmitheryMCP:
    def __init__(self, mcp_app):
        self.mcp_app = mcp_app

    async def handle_request(self, request):
        """Handle MCP requests with proper CORS headers"""
        # Set CORS headers
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            return {"status": 200, "headers": headers}

        # Handle health checks
        if request.path == "/health" and request.method == "GET":
            return {
                "status": 200,
                "headers": {**headers, "Content-Type": "application/json"},
                "body": '{"status": "healthy"}'
            }

        # Delegate to MCP app
        result = await self.mcp_app.handle_request(request)

        # Add CORS headers to response
        result["headers"] = {**result.get("headers", {}), **headers}
        return result

if __name__ == "__main__":
    import asyncio
    import uvloop
    from aiohttp import web

    # Create the MCP server
    mcp_server: FastMCP = create_server()

    # Get port from environment variable set by Smithery (default to 8080)
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    async def create_app():
        app = web.Application()
        smithery_mcp = SmitheryMCP(mcp_server)

        # Add MCP routes
        app.router.add_route("*", "/mcp", smithery_mcp.handle_request)
        app.router.add_route("*", "/health", smithery_mcp.handle_request)

        return app

    logger.info(f"Starting HTTP server on {host}:{port}")
    web.run_app(create_app(), host=host, port=port)
