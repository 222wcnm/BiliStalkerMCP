# Native FastMCP CLI

Prefer native FastMCP for terminal tasks. Use an existing authorized MCP config,
usually `.mcp.json`. The repository's `examples/native-cli.mcp.json` is a template:
replace its paths with absolute paths on the server machine, save a local copy,
and keep existing user configuration intact. The `/absolute/path/to/...` values
are placeholders: use Linux paths on Linux or paths such as `C:/path/to/...` on
Windows. JSON path strings do not expand shell variables like `$HOME`.
Choose commands for the actual shell; PowerShell examples assume PowerShell 7.
A single-server config preserves the tool names. Enable client UTF-8:

Bash / Linux:

```bash
export PYTHONUTF8=1
```

PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
```

Discover before calling (these commands work in either shell):

```sh
uv run fastmcp list .mcp.json
uv run fastmcp list .mcp.json --json
uv run fastmcp call .mcp.json search_users "keyword=中文 用户" limit=5 --json
uv run fastmcp call .mcp.json get_user_snapshot user_id_or_username=12345 video_limit=5 dynamic_limit=5 article_limit=0 --json
uv run fastmcp call .mcp.json get_video_detail bvid=BV1xx411c7mD fetch_subtitles=true subtitle_mode=smart subtitle_max_chars=12000 --json
uv run fastmcp call .mcp.json get_video_detail bvid=BV1xx411c7mD fetch_subtitles=true subtitle_format=anchors --json
uv run fastmcp call .mcp.json get_video_detail bvid=BV1xx411c7mD fetch_subtitles=true subtitle_format=segments subtitle_start_sec=240 subtitle_end_sec=300 --json
```

Read `structured_content.subtitles.full_text` in the default and anchors
formats. `tracks[].anchors` pairs 1-based transcript lines with times in that
part. Segments format returns `tracks[].segments` with exact text and times.
Use each track's `coverage` to compare source and returned subtitle bounds.
`tracks[].text` is an always-empty compatibility field. Check `returned_chars`
for text length, `scope.returned_pages` for page coverage, and `errors` and
`truncated` for partial text.

Read inputSchema for names, constraints, defaults and enum values. Ordinary
arguments use key=value; quote an entire argument when it contains spaces.
Omit unused optional values. For explicit null, nested objects or JSON files:

Bash / Linux:

```bash
uv run fastmcp call .mcp.json get_user_dynamics --input-json "$(cat args.json)" --json
```

PowerShell:

```powershell
uv run fastmcp call .mcp.json get_user_dynamics --input-json (Get-Content -Raw -Encoding utf8 args.json) --json
```

Configure credentials and proxies on the **server subprocess** in the config's
env, preferably using existing Cookie file paths. Parent BILI environment variables
are not automatically inherited. For an existing authorized `.env`, configure the
server args as `["run", "--env-file", "/absolute/path/to/.env", "bili-stalker-mcp", "serve"]`.
Do not embed secret values in examples or command arguments. Neither interface
automatically loads `.env`. The template sets server UTF-8 and ERROR logging;
set BILI_LOG_LEVEL and FASTMCP_LOG_LEVEL to INFO for diagnostics. Client UTF-8 must
also be enabled, especially for config files containing non-ASCII paths.

On success, --json returns content, is_error=false and structured_content.
Read structured_content as the business result, avoiding duplicate reading of the
text content. Check partial errors even on success.
Tool failures return is_error=true and text content; a text block may contain the
server's JSON error with reason, retry_after and request_id. Unknown tools,
connection failures and client argument failures can instead produce plain text,
even with --json. Always inspect the exit code before assuming valid JSON.
Correct parameters from the discovered schema; native validation does not provide
the legacy CLI's field suggestions. Respect retry_after; never retry rapidly.

Save long responses once, then inspect the file rather than repeating requests:

Bash / Linux:

```bash
uv run fastmcp call .mcp.json get_user_snapshot user_id_or_username=12345 --json > response.json
echo $?
```

PowerShell:

```powershell
uv run fastmcp call .mcp.json get_user_snapshot user_id_or_username=12345 --json > response.json
$LASTEXITCODE
```

Keep stderr separate. Native stdio calls start a new server per invocation; they
do not share caches between commands. Prefer a snapshot for broad overviews,
bounded pagination and reuse of saved results. Preserve video URL chapter selectors
and inspect subtitle coverage before interpreting transcripts.

Use `uv run bili-stalker-mcp doctor` for offline diagnostics in the intended
credential environment; it does not validate login. `doctor --network` explicitly
probes TCP connectivity. Cookie refresh remains opt-in and uses the existing setup.

Existing scripts can continue using [legacy CLI](legacy-cli.md), including its
raw business JSON, field repair hints and file/stdin input. Bare bili-stalker-mcp
still starts the MCP server; always give a query subcommand.
