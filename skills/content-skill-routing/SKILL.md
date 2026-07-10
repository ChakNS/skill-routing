---
name: content-skill-routing
description: Use when skill-routing dispatches a multi-stage content deliverable, or when the user explicitly wants a traceable content pipeline across evidence, strategy, writing, visual packaging, measurement, systems, and manual handoff. Use only when the final artifact is content or creator operations; do not claim generic technical research, code work, or router/catalog management.
compatibility: Requires the main skill-routing package and Python 3.10+ for deterministic planning.
---

# Content Skill Routing

## Role

Provide the content route-pack templates used by `skill-routing`. The main router owns local discovery, candidate ranking, missing-skill decisions, persistence, and cross-domain composition. This pack owns only content stages, conditions, dependencies, and candidate recommendations.

Read `references/pipeline-registry.json` only after the main router selects this pack. Read `references/platform-output-prep.md` only for the named platform and the matching part of `references/route-tables.md` when a stage boundary needs interpretation.

## Hard boundary

Prepare text, assets, metadata, and handoff checklists. Do not log in, upload, publish, like, comment, follow, collect, or message unless the user explicitly invokes a separate authorized publishing workflow.

## Execution rules

1. Use research only when evidence affects a content deliverable. Do not route generic technical/security research here.
2. Never fabricate sources, trends, comments, metrics, screenshots, cases, or platform behavior. Label assumptions.
3. Use `candidate_conditions`; Xiaohongshu art direction, Chinese humanization, full-page screenshots, card renderers, and image generation are conditional capabilities.
4. Treat candidate arrays as ordered alternatives unless `max_skills` explicitly permits more than one.
5. A missing candidate is resolved by the main router. Do not independently install or silently substitute another named skill.
6. Keep writing and asset stages serial unless the registry explicitly declares a safe parallel group.
7. Return saved asset paths when files are created and finish with a manual handoff when publishing is outside scope.

## Supported pipelines

- notes to a social post with hook, draft, polish, and handoff;
- Xiaohongshu/Rednote note package;
- evidence-backed article or newsletter;
- platform-neutral visual asset package;
- reusable content system and measurement inputs.

Use the compatibility CLI only for pack inspection:

```bash
python3 scripts/router_registry.py list pipelines
python3 scripts/router_registry.py explain <pipeline-id>
python3 scripts/router_registry.py validate
```

Actual personalized planning should use the main router's `plan-json` command.

## Report

`stage -> selected installed skill or fallback -> evidence/gate -> status`

Do not describe a missing recommendation as selected, and do not mark a planned stage as executed.
