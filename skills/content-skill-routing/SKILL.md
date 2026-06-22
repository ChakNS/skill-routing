---
name: content-skill-routing
description: Use when a content request needs a staged, traceable chain across research, strategy, writing, visual packaging, handoff, measurement, or content systems. Good fits include content packages, Xiaohongshu/Rednote notes, newsletters with sources, visual asset bundles, and content operating systems. Do not use it merely to pick one writing skill for a tiny edit.
---

# Content Skill Routing

## Purpose

Use this router before multi-stage content, creator operations, and content-system work. It turns a broad content request into a traceable chain of stages, candidate skills, dependencies, parallel groups, and handoff requirements.

This is an open-source router. Its public registry contains layered skill categories, stage definitions, recommended skill trees, and execution metadata. Installation may generate `references/local-skill-profile.generated.json` to mark which recommended skills are already present on the user's machine.

## Hard Boundary

This router prepares content and assets. It does not perform login-state platform automation, uploads, posting, commenting, liking, following, collecting, direct messaging, or real publishing.

For social platforms, produce publish-ready text, media assets, metadata, and a manual handoff checklist. The user publishes manually.

## Load Order

1. Read this file.
2. For simple one-shot edits or titles, use this file alone unless the route is ambiguous.
3. For non-trivial content work, read only the matching section in `references/route-tables.md`.
4. If a platform is named, read only the matching section in `references/platform-output-prep.md`.
5. For multi-stage work, read `references/pipeline-registry.json` to choose a layered stage-by-stage pipeline.
6. If present, read `references/local-skill-profile.generated.json` to know which recommended skills are installed.
7. Load selected downstream skills only when installed and when their stage is about to execute.

If a recommended downstream skill is missing, state the recommendation and continue with the best available general approach.

## Complexity Gate

Use this router when the task crosses at least two meaningful stages, such as research -> draft, title -> draft -> handoff, or visual direction -> asset generation -> handoff.

Skip this router for tiny copy edits, one title, one paragraph rewrite, or a simple summary unless the user asks for routing traceability. In those cases, use the directly relevant downstream skill or answer directly.

## Orchestration Model

Use the clarification gate only when the missing answer changes the route or final artifact. Do not ask for routine preferences when a reasonable default is available.

Ask before routing when:

- The platform, deliverable, source material, or success condition is unclear.
- The request could mean materially different workflows.
- A required asset is missing and cannot be safely assumed.

Do not ask before routing when:

- The platform and deliverable are clear.
- The task is a small edit, title, rewrite, summary, or one-shot draft.
- The remaining uncertainty affects only style; state the assumption and continue.

## Pipeline Decomposition

For sequential work, decompose into stages such as `intake`, `research`, `topic`, `title_hook`, `draft`, `voice_polish`, `visual_direction`, `asset_generation`, `render`, `handoff`, `measurement`, and `systemization`.

Use registry layers to explain why each skill is selected:

- `intake`: clarify platform, audience, deliverable, and source material.
- `evidence`: gather sources, examples, screenshots, analytics, or user-provided material.
- `strategy`: choose positioning, angle, and operating approach.
- `creation`: create topics, hooks, drafts, scripts, edits, and voice polish.
- `packaging`: create covers, cards, thumbnails, screenshots, generated images, and visual systems.
- `handoff`: prepare publish-ready manual packages.
- `measurement`: review performance and choose next experiments.
- `systems`: build reusable workflows and content libraries.

Do not load every recommended skill in a pipeline upfront. Select the current stage, check the generated local profile, then either load an installed skill or recommend a missing one.

## Parallel Agent Routing

When `pipeline-registry.json` marks multiple stages with the same `step` and `parallel_group`, prefer running those stages with separate agents when the work is independent. Good content examples are research vs visual direction, title exploration vs cover direction, or analytics review vs system design inputs.

Do not parallelize when stages write the same final artifact, depend on an unresolved prior decision, require the same scarce external session, or would create conflicting final copy. Merge parallel branch outputs in the next serial stage and record which branch produced which evidence or asset.

## Evidence Red Line

For research, trend claims, competitor analysis, market judgment, user demand, strategy, and factual content:

- Do not fabricate facts, comments, examples, metrics, screenshots, platform trends, or case studies.
- Use retrieved sources, user-provided material, local project data, or clearly marked assumptions.
- Mark unverified claims as unverified.
- Strategy recommendations must trace to evidence or be labeled as judgment.

## Routing Report

For multi-stage work, finish with a compact report:

`stage -> selected skill or recommendation -> reason -> evidence/gate -> status`

Mention missing recommended skills only when they would materially improve the result.
For parallel groups, include the group name and say how the branch outputs were merged.

## CLI

Use `scripts/router_registry.py` for read-only inspection:

```bash
python3 scripts/router_registry.py list skills
python3 scripts/router_registry.py list pipelines
python3 scripts/router_registry.py plan "make a LinkedIn post from these notes and prepare a manual handoff"
python3 scripts/router_registry.py plan-json "make a LinkedIn post from these notes and prepare a manual handoff"
python3 scripts/router_registry.py validate
```

## Public References

- `references/pipeline-registry.json`: structured stage, skill, and pipeline recommendations.
- `references/route-tables.md`: route notes by content domain.
- `references/platform-output-prep.md`: manual handoff formats.
- `references/routing-fixtures.md`: regression examples.
- `references/local-skill-profile.generated.json`: optional generated local capability map.

## Common Mistakes

- Treating publish prep as real publishing.
- Drafting factual content without evidence.
- Loading several adjacent writing skills when one primary skill plus one quality pass is enough.
- Failing when a recommended downstream skill is missing.
- Recommending a local-only skill as mandatory public behavior.
