import argparse
import asyncio
import io
import json
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Never

from . import __version__

logger = logging.getLogger(__name__)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        _write_error("invalid_arguments", message)
        raise SystemExit(2)


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
    log_level = getattr(
        logging, os.environ.get("BILI_LOG_LEVEL", "INFO").upper(), logging.INFO
    )

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonLogFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(handler)


def _close_http_client_sync() -> None:
    from .infra.http_client import close_shared_http_client

    try:
        asyncio.run(close_shared_http_client())
    except RuntimeError:
        # Best-effort cleanup only.
        pass


def _serve() -> int:
    """Preserve the existing MCP stdio entrypoint."""
    try:
        from bili_stalker_mcp.server import create_server

        _configure_logging()

        logger.info(
            "server_starting", extra={"event": "server_starting", "transport": "stdio"}
        )

        mcp = create_server()
        mcp.run(transport="stdio")

    except ImportError as exc:
        print(f"Import error: {exc}", file=sys.stderr)
        print("Ensure the project is installed (uv pip install -e .)", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("server_start_failed", extra={"event": "server_start_failed"})
        return 1
    finally:
        _close_http_client_sync()

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Query Bilibili tools directly or run the MCP stdio server.",
        epilog="Without a subcommand, starts the MCP stdio server (same as serve).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Start the MCP stdio server")
    doctor = commands.add_parser("doctor", help="Check local configuration")
    doctor.add_argument(
        "--network", action="store_true", help="Also test TCP connectivity"
    )

    tools = commands.add_parser("tools", help="List tools or inspect one tool's schema")
    tools.add_argument("tool", nargs="?", help="Tool name to inspect")
    tools.add_argument("--pretty", action="store_true", help="Indent the JSON output")

    call = commands.add_parser(
        "call", help="Call a tool once and print its JSON result"
    )
    call.add_argument("tool", help="Tool name, e.g. get_user_snapshot")
    arguments = call.add_mutually_exclusive_group()
    arguments.add_argument("--args", default="{}", help="Arguments as a JSON object")
    arguments.add_argument(
        "--args-file", metavar="PATH", help="Read a UTF-8 JSON file, or - for stdin"
    )
    call.add_argument("--pretty", action="store_true", help="Indent the JSON output")
    return parser


def _read_arguments(args: argparse.Namespace) -> dict[str, Any]:
    raw = args.args
    if args.args_file == "-":
        raw = sys.stdin.read()
    elif args.args_file is not None:
        raw = Path(args.args_file).read_text(encoding="utf-8-sig")
    arguments = json.loads(raw.lstrip("\ufeff"))
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return arguments


def _write_json(payload: object, *, pretty: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def _write_error(reason: str, message: str) -> None:
    # ToolError may already contain the server's sanitized error, including
    # risk-control codes and retry_after. Preserve that structured payload.
    try:
        error = json.loads(message)
    except json.JSONDecodeError:
        error = None
    if not isinstance(error, dict):
        error = {"reason": reason, "message": message}
    print(json.dumps({"error": error}, ensure_ascii=False), file=sys.stderr)


async def _execute(args: argparse.Namespace, arguments: dict[str, Any]) -> object:
    from fastmcp.exceptions import NotFoundError

    from .infra.http_client import close_shared_http_client
    from .server import create_server

    try:
        mcp = create_server()
        if args.command == "tools" and args.tool is None:
            return [
                {"name": tool.name, "description": tool.description}
                for tool in await mcp.list_tools()
            ]

        tool = await mcp.get_tool(args.tool)
        if tool is None:
            raise NotFoundError(
                f"Unknown tool: {args.tool!r}. Use 'tools' to list names."
            )
        if args.command == "tools":
            return tool.to_mcp_tool().model_dump(mode="json", exclude_none=True)

        result = await mcp.call_tool(args.tool, arguments)
        if result.structured_content is None:
            raise RuntimeError("Tool returned no structured result")
        return result.structured_content
    finally:
        # Close connections on the same event loop that ran the request.
        await close_shared_http_client()


def _run_command(args: argparse.Namespace) -> int:
    from fastmcp.exceptions import NotFoundError, ToolError, ValidationError
    from pydantic import ValidationError as PydanticValidationError

    from .cookie_refresh import CookieRefreshConfigError
    from .errors import public_error_json

    arguments: dict[str, Any] = {}
    if args.command == "call":
        try:
            arguments = _read_arguments(args)
        except (ValueError, OSError) as exc:
            _write_error("invalid_arguments", str(exc))
            return 2

    # FastMCP logs chained exceptions, which can undo the server's error
    # sanitization. The server metrics and the CLI error below already report
    # failures without exposing the original upstream exception.
    tool_logger = logging.getLogger("fastmcp.server.server")
    was_disabled = tool_logger.disabled
    tool_logger.disabled = True
    try:
        payload = asyncio.run(_execute(args, arguments))
    except (NotFoundError, ValidationError, PydanticValidationError) as exc:
        _write_error("invalid_arguments", str(exc))
        return 2
    except CookieRefreshConfigError as exc:
        _write_error("configuration_error", str(exc))
        return 1
    except ToolError as exc:
        _write_error("tool_error", str(exc))
        return 1
    except Exception as exc:
        _write_error("internal_error", public_error_json(exc))
        return 1
    finally:
        tool_logger.disabled = was_disabled

    _write_json(payload, pretty=args.pretty)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run a query command, or the backwards-compatible MCP stdio server."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args(argv)
    try:
        if args.command in (None, "serve"):
            return _serve()
        if args.command == "doctor":
            from .doctor import run_doctor

            try:
                report = run_doctor(network=args.network)
            except Exception as exc:
                from .errors import public_error_json

                _write_error("internal_error", public_error_json(exc))
                return 1
            _write_json(report)
            return 0 if report["ok"] else 1
        _configure_logging()
        return _run_command(args)
    except ImportError as exc:
        _write_error("import_error", f"{exc}. Install the project with 'uv sync'.")
        return 1
    except KeyboardInterrupt:
        _write_error("interrupted", "Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
