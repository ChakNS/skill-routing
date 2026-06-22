# Content Route Tables

Use this file only after `content-skill-routing/SKILL.md` identifies a non-trivial content task.

## Creation

Use for posts, articles, newsletters, scripts, rewrites, hooks, and titles.

Default route:

1. `title_hook` when the opening or title affects success.
2. `draft` for the main artifact.
3. `voice_polish` for final platform formatting.
4. `handoff` for publish-ready text and metadata.

Recommended skills are in `pipeline-registry.json`. If the profile says a skill is missing, recommend it and continue with a general draft.

## Research

Use when facts, examples, competitors, trends, or source citations matter.

Default route:

1. `research`
2. `topic`
3. `draft`
4. `handoff`

Do not invent evidence. Mark assumptions explicitly.

## Visual Packaging

Use for covers, cards, carousels, thumbnails, image generation, and full-page screenshots.

Default route:

1. `visual_direction`
2. `asset_generation`
3. `handoff`

If the user asked for a full-page screenshot, prefer the screenshot recommendation over image/card generation.

## Measurement

Use when the user provides analytics exports, performance notes, or wants a diagnosis.

Default route:

1. `measurement`
2. `strategy`
3. `topic`

Prefer evidence-backed next actions over generic advice.

## Systems

Use when the user wants calendars, content libraries, operating docs, reusable workflows, or knowledge capture.

Default route:

1. `strategy`
2. `systemization`
3. `measurement`
