
import logging
import os
import sys

logger = logging.getLogger(__name__)

def main():
    """主CLI入口点，直接启动MCP服务器与客户端通信"""
    try:
        from bili_stalker_mcp.server import create_server

        # 获取并设置日志级别环境变量（默认为WARNING，避免过多输出）
        log_level = getattr(logging, os.environ.get("BILI_LOG_LEVEL", "WARNING").upper())
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,  # 确保日志输出到stderr，不干扰stdout（用于MCP协议）
        )

        logger.info("🚀 Starting BiliStalkerMCP server...")
        logger.info("Note: Server startup logs will only appear here in debug mode (set BILI_LOG_LEVEL=INFO)")

        mcp = create_server()
        mcp.run(transport="stdio")

    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保项目已正确安装 (uv pip install -e .)")
        return
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")
        logger.exception("Server failed to start")
        return

if __name__ == "__main__":
    main()
