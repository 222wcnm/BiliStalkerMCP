"""Exercise the public stdio protocol with MCP 2 or an MCP 1 client.

Run with a client interpreter and point --server-python at the locked MCP 2
environment. The fixture replaces upstream calls, so this test needs no cookie.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXPECTED_NAMES = {
    "search_users",
    "get_user_snapshot",
    "get_user_info",
    "get_user_videos",
    "search_user_videos",
    "get_video_detail",
    "get_user_dynamics",
    "get_user_articles",
    "get_article_content",
    "get_user_followings",
    "get_content_comments",
    "get_content_comment_replies",
}
USER = {"mid": 123, "name": "协议冒烟用户"}


def install_fixture():
    from bili_stalker_mcp import server

    async def credential(_ctx):
        return object()

    async def user_info(uid, cred):
        if uid == 999:
            raise RuntimeError("fixture upstream failure")
        return {**USER, "mid": uid}

    server._get_credential_from_context = credential
    server.fetch_user_info = user_info
    return server


async def smoke(server_python: str, mode: str) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    source = Path(__file__).resolve().parents[1]
    child_env = os.environ.copy()
    child_env.update(
        {
            "PYTHONPATH": str(source),
            "BILI_COOKIE_FILE": "",
            "BILI_ENABLE_COOKIE_REFRESH": "false",
            "BILI_PROXY": "",
        }
    )
    params = StdioServerParameters(
        command=server_python,
        args=[str(Path(__file__).resolve()), "--serve-fixture"],
        cwd=str(source),
        env=child_env,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            if mode == "default":
                if not hasattr(session, "discover"):
                    raise AssertionError("Default discovery needs an MCP 2 client")
                await session.discover()
            else:
                await session.initialize()

            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == EXPECTED_NAMES
            assert all(
                getattr(tool, "output_schema", None)
                or getattr(tool, "outputSchema", None)
                for tool in tools.tools
            )
            assert all(
                "ctx"
                not in getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))[
                    "properties"
                ]
                for tool in tools.tools
            )

            prompts = await session.list_prompts()
            assert {item.name for item in prompts.prompts} == {
                "track_user_updates",
                "analyze_user_activity",
            }
            prompt = await session.get_prompt("track_user_updates")
            assert prompt.messages

            result = await session.call_tool(
                "get_user_info", {"user_id_or_username": "123"}
            )
            assert not getattr(result, "is_error", getattr(result, "isError", None))
            assert (
                getattr(
                    result,
                    "structured_content",
                    getattr(result, "structuredContent", None),
                )
                == USER
            )

            try:
                invalid = await session.call_tool("get_user_info", {})
            except Exception:
                pass  # Older clients raise for protocol-level parameter errors.
            else:
                assert getattr(invalid, "is_error", getattr(invalid, "isError", None))

            failed = await session.call_tool(
                "get_user_info", {"user_id_or_username": "999"}
            )
            assert getattr(failed, "is_error", getattr(failed, "isError", None))

    def run_cli(*arguments: str, input_text: str | None = None):
        return subprocess.run(
            [server_python, str(Path(__file__).resolve()), "--cli-fixture", *arguments],
            cwd=source,
            env=child_env,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    catalog = run_cli("tools")
    assert catalog.returncode == 0, catalog.stderr
    assert {item["name"] for item in json.loads(catalog.stdout)} == EXPECTED_NAMES
    with tempfile.TemporaryDirectory(prefix="bili-cli-stdio-") as directory:
        arguments = Path(directory) / "参数.json"
        arguments.write_text('\ufeff{"user_id_or_username":"123"}', encoding="utf-8")
        for argument_source, input_text in (
            (str(arguments), None),
            ("-", '\ufeff{"user_id_or_username":"123"}'),
        ):
            cli = run_cli(
                "call",
                "get_user_info",
                "--args-file",
                argument_source,
                input_text=input_text,
            )
            assert cli.returncode == 0, cli.stderr
            assert json.loads(cli.stdout) == USER

    usage_error = run_cli("call", "get_user_info", "--args", "{}")
    assert usage_error.returncode == 2 and not usage_error.stdout
    assert json.loads(usage_error.stderr.splitlines()[-1])["error"]["reason"] == (
        "invalid_arguments"
    )
    tool_error = run_cli(
        "call", "get_user_info", "--args", '{"user_id_or_username":"999"}'
    )
    assert tool_error.returncode == 1 and not tool_error.stdout
    assert json.loads(tool_error.stderr.splitlines()[-1])["error"]["reason"] == (
        "internal_error"
    )
    print(f"{mode}: 12 tools, 2 prompts, context, errors, CLI parity OK")


def main() -> None:
    if "--cli-fixture" in sys.argv:
        index = sys.argv.index("--cli-fixture")
        install_fixture()
        from bili_stalker_mcp.cli import main as cli_main

        raise SystemExit(cli_main(sys.argv[index + 1 :]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--server-python")
    parser.add_argument("--mode", choices=("default", "legacy"), default="default")
    parser.add_argument("--serve-fixture", action="store_true")
    args = parser.parse_args()
    if args.serve_fixture:
        install_fixture().create_server().run(transport="stdio")
    else:
        if not args.server_python:
            parser.error("--server-python is required")
        asyncio.run(smoke(args.server_python, args.mode))


if __name__ == "__main__":
    main()
