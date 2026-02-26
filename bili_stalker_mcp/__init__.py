"""
BiliStalkerMCP package

MCP Server for Bilibili user content intelligence.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bili_stalker_mcp")
except PackageNotFoundError:
    __version__ = "3.0.0"  # fallback

__author__ = "222wcnm"
__email__ = "2328072813li@gmail.com"
__license__ = "MIT"
__description__ = "MCP Server for Bilibili user content intelligence"
__url__ = "https://github.com/222wcnm/BiliStalkerMCP"
