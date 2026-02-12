"""
BiliStalkerMCP package

MCP Server for getting Bilibili user video updates
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bili_stalker_mcp")
except PackageNotFoundError:
    __version__ = "2.7.0"  # fallback

__author__ = "222wcnm"
__email__ = "2328072813li@gmail.com"
__license__ = "MIT"
__description__ = "MCP Server for getting Bilibili user video updates"
__url__ = "https://github.com/222wcnm/BiliStalkerMCP"