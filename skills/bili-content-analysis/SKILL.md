---
name: bili-content-analysis
description: Deep analysis and tracking of Bilibili creators, videos, dynamics, and articles with BiliStalker MCP tools. Use when users ask for transcript interpretation, timeline reconstruction, theme extraction, behavior analysis, recent shift tracking, or discussion grounded in fetched Bilibili source material.
---

# Bili Content Analysis

## Run workflow

1. Clarify target and scope
- Extract target identifier from user input (`uid`/username, `bvid`, `article_id`, keyword).
- Keep response language aligned with the user unless explicitly requested otherwise.
- Ask for missing identifiers only when tools cannot resolve them safely.

2. Collect minimum sufficient evidence
- Prefer lightweight list tools first and fetch heavy detail only for high-value items.
- Use this default sequence:
1) `get_user_info`
2) `get_user_videos` or `search_user_videos`
3) `get_video_detail` for selected videos
4) `get_user_dynamics`
5) `get_user_articles`
6) `get_article_content` for selected articles

3. Reconstruct source before interpreting
- Preserve source structure by timeline, chapter, or original logic order.
- Correct obvious transcription noise only when context provides strong evidence.
- Distinguish speakers when style, viewpoint, or surrounding context supports separation.

4. Build the analysis
- Explain facts, logic chain, assumptions, evidence, themes, and recent shifts.
- Mark inferred conclusions explicitly when they are not directly stated by the source.
- Preserve original wording and tone where it carries analytical value.

5. Keep output useful for downstream tasks
- Keep key anchors in output: `uid`, `bvid`, `article_id`, publish times, and key source snippets.
- Avoid fragmented one-line bullet dumps; keep coherent narrative blocks with clear headings.

6. Handle failures safely
- If required data is missing or retrieval fails, state exact blockers and stop speculation.
- Provide concrete next actions (for example: request missing id, retry with cursor/page, fetch detail for candidate items).

## Output contract

- Start with the final analysis directly when context is sufficient.
- Skip method narration unless the user asks for it.
- Match depth to intent: brief asks get concise conclusions plus key evidence; deep asks get full reconstruction and multi-dimensional interpretation.

## Load detailed style rules on demand

- Read [references/analysis-style.md](references/analysis-style.md) when detailed style constraints are required.
- Follow system and developer instructions first if any conflict appears.
