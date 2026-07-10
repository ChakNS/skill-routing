---
name: coding-skill-routing
description: Use when skill-routing dispatches a multi-stage software task, or when the user explicitly wants a traceable coding pipeline across design, implementation, debugging, testing, review, browser verification, or release. Use for code deliverables, not general content research or router/catalog management. For a single obvious local skill, let skill-routing use the direct route instead.
compatibility: Requires the main skill-routing package and Python 3.10+ for deterministic planning.
---

# Coding Skill Routing

## Role

Provide the software route-pack templates used by `skill-routing`. The main router owns local discovery, candidate ranking, missing-skill decisions, persistence, and cross-domain composition. This pack owns only software stages, conditions, dependencies, and candidate recommendations.

Read `references/pipeline-registry.json` only after the main router selects this pack. Read the matching section of `references/route-tables.md` when a stage boundary needs interpretation.

## Execution rules

1. Inspect project rules and nearby implementation patterns before edits.
2. Use `candidate_conditions`; do not load Next.js, shadcn, Supabase, OpenAI, PR, or deploy skills merely because they are listed somewhere in the pack.
3. Treat candidate arrays as ordered alternatives unless `max_skills` explicitly permits more than one.
4. Follow declared dependencies. Test-first stages precede production edits in feature, bug, backend, skill, and OpenAI pipelines.
5. A missing candidate is resolved by the main router. Do not independently install or silently substitute another named skill.
6. External writes require explicit user intent: commits, PRs, deploys, migrations, cloud changes, credentials, and production operations.
7. Finish only with fresh verification evidence.

## Supported pipelines

- feature design and implementation;
- bug reproduction and fix;
- frontend/UI change with browser and visual QA;
- backend/API/data/auth change;
- skill or plugin development;
- testing and test-suite repair;
- code and pull-request review;
- OpenAI API work;
- explicitly requested commit, PR, or deployment preparation.

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
