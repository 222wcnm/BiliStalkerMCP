import json
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from .infra.http_client import close_shared_http_client

logger = logging.getLogger(__name__)


class JsonLogFormatter(logging.Formatter):
    """Structured JSON formatter used by default for MCP server logs."""

    _reserved = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in self._reserved or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    log_level = getattr(logging, os.environ.get("BILI_LOG_LEVEL", "INFO").upper(), logging.INFO)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonLogFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)


def _close_http_client_sync() -> None:
    try:
        asyncio.run(close_shared_http_client())
    except RuntimeError:
        # Best-effort cleanup only.
        pass


def main() -> None:
    """CLI entrypoint for MCP stdio transport."""
    try:
        from bili_stalker_mcp.server import create_server

        _configure_logging()

        logger.info("server_starting", extra={"event": "server_starting", "transport": "stdio"})

        mcp = create_server()
        mcp.run(transport="stdio")

    except ImportError as exc:
        print(f"Import error: {exc}", file=sys.stderr)
        print("Ensure the project is installed (uv pip install -e .)", file=sys.stderr)
    except Exception:
        logger.exception("server_start_failed", extra={"event": "server_start_failed"})
    finally:
        _close_http_client_sync()


if __name__ == "__main__":
    main()
