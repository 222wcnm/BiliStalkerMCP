
import logging

logger = logging.getLogger(__name__)

def main():
    """主CLI入口点，直接启动MCP服务器与客户端通信"""
    try:
        from bili_stalker_mcp.server import create_server

        print("🚀 Starting BiliStalkerMCP server...", flush=True)
        logger.info("BiliStalkerMCP server starting up...")

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
