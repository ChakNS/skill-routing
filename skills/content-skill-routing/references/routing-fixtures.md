# Routing Fixtures

Use these as manual regression prompts.

## Social Post

Prompt: "Turn these messy notes into a LinkedIn post and give me three hooks."

Expected route: `social_post_from_notes`, with `draft`, `title_hook`, and `handoff`.

## Rednote Package

Prompt: "帮我做一篇小红书图文，主题是 AI 工作流，包含标题、正文和封面方向。"

Expected route: `xhs_note_package`, with manual publish boundary.

## Evidence-Backed Article

Prompt: "Research the latest creator economy examples and write a newsletter with sources."

Expected route: `researched_article`, with evidence required.

## Visual Asset

Prompt: "Create a shareable full-page screenshot of this prototype."

Expected route: `visual_asset_package`, with screenshot recommendation preferred.
