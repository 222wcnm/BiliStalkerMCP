"""
BiliStalkerMCP 命令行入口

此模块提供命令行接口来启动 BiliStalkerMCP 服务器。
"""

import logging
from .server import run

logger = logging.getLogger(__name__)

def main():
    """启动 BiliStalkerMCP 服务器的命令行入口"""
    logger.info("Starting BiliStalkerMCP via CLI...")
    run()

if __name__ == "__main__":
    main()