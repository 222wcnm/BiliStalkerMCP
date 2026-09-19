---
name: bili-content-analysis
description: Deep analysis and tracking of Bilibili creators, videos, dynamics, and articles with BiliStalker MCP tools or CLI. Use when users ask for transcript interpretation, timeline reconstruction, theme extraction, behavior analysis, recent shift tracking, or discussion grounded in fetched Bilibili source material.
---

# Bili Content Analysis

## Choose an available interface

- Use the user's requested interface. Otherwise use connected BiliStalker MCP tools, or the CLI when terminal access and the project are available.
- For CLI invocation, read [references/cli.md](references/cli.md). Discover tool names with `bili-stalker-mcp tools` and inspect arguments with `bili-stalker-mcp tools TOOL`; the CLI shares MCP tool names, schemas, and results.
- Use credentials configured for the chosen runtime. An MCP client's environment settings do not automatically apply to a separate terminal.

## Run workflow

1. Clarify target and scope
- Extract target identifier from user input (`uid`/username, `bvid`, `article_id`, keyword).
- Resolve usernames with `search_users` and reuse the selected numeric UID. Ask when candidates cannot be distinguished from the user's context.
- Keep response language aligned with the user unless explicitly requested otherwise.
- Ask for missing identifiers only when tools cannot resolve them safely.

2. Collect minimum sufficient evidence
- For a broad user overview, start with `get_user_snapshot`; set unneeded section limits to 0 and check `errors` for incomplete sections.
- For a specific video or article, fetch its detail directly. Video transcripts require `fetch_subtitles=true`; use `smart` and a suitable `subtitle_max_chars` unless broader subtitle coverage is needed.
- Use `get_user_videos`, `search_user_videos`, `get_user_dynamics`, or `get_user_articles` for targeted discovery and deeper pagination. Prefer lightweight lists and fetch heavy detail only for selected items.
- For discussion analysis, use `get_content_comments` and fetch a selected thread with `get_content_comment_replies`. Note-style comments may be previews; retrieve `note.cvid` with `get_article_content` when full text is needed.

3. Reconstruct source before interpreting
- Preserve source structure by timeline, chapter, or original logic order.
- Correct obvious transcription noise only when context provides strong evidence.
- Distinguish speakers when style, viewpoint, or surrounding context supports separation.

4. Build the analysis
- Explain facts, logic chain, assumptions, evidence, themes, and recent shifts.
- Describe recent patterns from the observed sample; infer a change over time only when earlier material provides a comparable baseline.
- Mark inferred conclusions explicitly when they are not directly stated by the source.
- Preserve original wording and tone where it carries analytical value.

5. Keep output useful for downstream tasks
- Keep key anchors in output: `uid`, `bvid`, `article_id`, publish times, and key source snippets.
- Avoid fragmented one-line bullet dumps; keep coherent narrative blocks with clear headings.

6. Handle failures safely
- If required data is missing or retrieval fails, state exact blockers and stop speculation.
- Treat partial snapshots and unavailable subtitles as incomplete evidence. Respect a returned `retry_after` instead of immediately repeating blocked queries.
- Provide concrete next actions (for example: request missing id, retry with cursor/page, fetch detail for candidate items).

## Output contract

- Start with the final analysis directly when context is sufficient.
- Skip method narration unless the user asks for it.
- Match depth to intent: brief asks get concise conclusions plus key evidence; deep asks get full reconstruction and multi-dimensional interpretation.

## Load detailed style rules on demand

- Read [references/analysis-style.md](references/analysis-style.md) when detailed style constraints are required.
- Follow system and developer instructions first if any conflict appears.
