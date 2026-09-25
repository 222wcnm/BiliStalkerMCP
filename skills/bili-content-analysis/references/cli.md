# BiliStalker CLI

Use the CLI when the task runs in a terminal and BiliStalker is installed or a local
checkout is available. It executes the same tools as MCP in one process and exits
after printing the result.

## Locate the command

For an installed package, use `bili-stalker-mcp`. From a source checkout, prefix it
with `uv run`. When working elsewhere, specify the known checkout path:

```powershell
uv run --directory /path/to/BiliStalkerMCP bili-stalker-mcp --help
```

`uv run python -m bili_stalker_mcp` is another entrypoint from the checkout.
Use a version whose help lists `tools` and `call`. If those commands are missing,
use an available updated checkout or report that the installed version needs an
update. Copying this skill alone does not install the CLI.

Always provide a subcommand for queries: no arguments, or `serve`, starts the
long-running MCP stdio server.

## Discover and call tools

The examples below run from the checkout. Substitute real IDs from the request or
retrieved results.

```powershell
uv run bili-stalker-mcp tools
uv run bili-stalker-mcp tools get_user_snapshot --pretty
uv run bili-stalker-mcp call search_users --args '{"keyword":"用户名","limit":5}'
uv run bili-stalker-mcp call get_user_snapshot --args '{"user_id_or_username":"12345","video_limit":5,"dynamic_limit":5,"article_limit":0}'
uv run bili-stalker-mcp call get_video_detail --args '{"bvid":"BV1xx411c7mD","fetch_subtitles":true,"subtitle_mode":"smart","subtitle_max_chars":12000}'
```

`tools` returns names and descriptions. `tools TOOL` returns the complete schema;
use `inputSchema` for required fields, defaults, types, bounds, and enum values.
Use the same underscore-separated names and JSON keys as MCP, including tools for
articles, followings, comments, and replies. `call TOOL` defaults to an empty
argument object when no argument source is supplied.

Keep string IDs quoted, especially article and dynamic IDs that exceed JavaScript's
safe integer range. JSON booleans are `true`/`false`; optional cursors can be omitted
or `null`. Pass returned `next_cursor` values unchanged. Keep the comment sort order
unchanged while paging; page-based tools start at page 1.

Use `--args-file PATH` for a UTF-8 JSON object (a BOM is accepted), or `--args-file -`
for stdin. Choose one argument source per call. This avoids shell-specific quoting
problems and is useful for long cursors:

```powershell
@{ user_id_or_username = "12345"; limit = 5 } | ConvertTo-Json -Compress | uv run bili-stalker-mcp call get_user_dynamics --args-file -
uv run bili-stalker-mcp call get_user_snapshot --args-file args.json --pretty
```

## Credentials and output

Run `bili-stalker-mcp doctor` when local configuration blocks a query. It prints
JSON diagnostics without making network requests, changing credential files, or
printing secret values. Use `doctor --network` only when a TCP connectivity check
is needed; it does not verify login or an API response.

The CLI reads the same environment variables as MCP: `SESSDATA` or
`BILI_COOKIE_FILE`, optional `BILI_JCT`/`BUVID3`, and `BILI_PROXY` when configured.
Use existing authorized credential files or environment settings without printing
their contents or putting secrets in command arguments. A terminal does not inherit
an MCP client's private `env` block. Report missing credentials when they block a
query; help, version, and tool discovery need no login.

If the checkout has an existing authorized `.env` file, load it explicitly with
`uv run --env-file .env bili-stalker-mcp ...`. Neither the CLI nor plain `uv run`
automatically loads `.env`. Prefer this process-local loading over copying
credential values into commands or changing global environment settings.

Automatic Cookie refresh remains opt-in via `BILI_ENABLE_COOKIE_REFRESH=true` with
existing Cookie and refresh-token files. Reuse the project's refresh setup; changing
interfaces does not require enabling refresh or changing credentials.

On success, stdout contains one UTF-8 JSON value with the tool's result directly.
`--pretty` adds indentation. Capture stdout separately from stderr so logs cannot
contaminate JSON parsing. A snapshot's `errors` field identifies sections that
failed even when the command succeeded; missing sections are not evidence of no
activity. Subtitle retrieval can also degrade within a successful video response.

When saving evidence or reusing a large result, capture the original stdout to a
UTF-8 JSON file on the first call and analyze that file. Keep summaries separate
from the raw result so later verification does not require another upstream request.

Exit codes:

- `0`: the command succeeded; inspect any partial-result indicators.
- `1`: a query, credential, or runtime failure.
- `2`: invalid command, unknown tool, unreadable argument file, or invalid arguments.
- `130`: the user interrupted execution.

Query failures leave stdout empty and end stderr with a JSON `error` object.
Argument-parser errors use the same JSON format. Error objects preserve available
server fields such as `reason`, `code`, `retry_after`, and `request_id`. Respect
`retry_after` for risk-control failures and report unavailable evidence instead of
issuing rapid repeat queries.
