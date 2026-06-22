---
name: skill-routing
description: Use when managing, installing, inspecting, validating, or dispatching a workflow routing matrix that composes multiple skills into staged, traceable task chains. Use this main router when the user asks about router modules, skill paths, routing behavior, installed skills, recommended skill trees, cross-domain routing, plan-json output, or routing evals. Do not use it merely as a generic one-step skill selector.
---

# Skill Routing

## Purpose

Use this main router to manage and dispatch router modules. It is the lightweight orchestration layer for a workflow routing matrix:

- `content-skill-routing` handles content, writing, creator operations, visual packaging, and manual publish handoff.
- `coding-skill-routing` handles programming, debugging, testing, UI, deployment, GitHub, and skill/plugin work.

The main router does not execute content or coding tasks itself. It lists modules, validates module registries, chooses the correct domain router, and returns a traceable chain that can be read by a human or consumed as JSON.

## Value Boundary

Do not position this router as "the thing that makes agents recognize skills." Modern agents can often trigger a single skill from a good `description`.

Use this router when the value is the chain:

- a task needs multiple stages, not one skill call;
- the stage order matters;
- some stages can safely run in parallel;
- the final answer should explain which skills or fallbacks were used;
- the route should be testable through fixtures or evals.

For small one-shot tasks, skip the router and use the obvious downstream skill directly.

## Architecture

- Main router: module registry, cross-router listing, validation, and dispatch rules.
- Router modules: domain-specific task decomposition, layered stage categories, pipeline templates, skill candidates, serial/parallel execution metadata, ambiguity gates, and completion reports.
- Downstream skills: actual execution of writing, coding, research, UI, testing, packaging, deployment, and other work.

## Domain Registry Shape

Domain routers should keep their execution model in `references/pipeline-registry.json`:

- `layers`: broad skill categories such as evidence, creation, packaging, build, quality, and release.
- `stages`: small task phases, each assigned to a layer.
- `skills`: recommended downstream skills with category, layer, stages, and whether they are safe to run in parallel.
- `pipelines`: ordered stages with `step`, optional `depends_on`, optional `parallel_group`, and `agent_role`.

When multiple stages share the same `step` and `parallel_group`, the domain router may dispatch them to separate agents if their inputs and write targets do not conflict. The next serial stage is responsible for merging branch outputs and reporting the process clearly.

## Load Order

1. Read this file.
2. Read `references/router-modules.json` when listing, validating, adding, removing, or dispatching modules.
3. For a concrete content task, read only `content-skill-routing/SKILL.md` and its registry.
4. For a concrete software task, read only `coding-skill-routing/SKILL.md` and its registry.
5. Load downstream skills only after the selected domain router chooses them and confirms they are available or explicitly recommends installation.

## Routing Rule

Stay in this main router when the user asks to:

- Install, open-source, inspect, or validate routing skills.
- Change module registration or skill paths.
- Understand which domain router should handle a task.
- Check which recommended downstream skills are installed.

Dispatch to `content-skill-routing` for content, writing, social, creator, publishing-prep, visual-card, thumbnail, newsletter, or content-system tasks.

Dispatch to `coding-skill-routing` for code, repositories, debugging, tests, UI implementation, backend/data, deployments, GitHub, automation, OpenAI API, skill/plugin, or agent development tasks.

If a request has both content and coding work, decompose it and route stages separately.

## Local Profiles

This open-source router expects installations to generate local profiles. The installer scans existing skills and writes:

- `content-skill-routing/references/local-skill-profile.generated.json`
- `coding-skill-routing/references/local-skill-profile.generated.json`

Treat those files as capability maps, not dependencies. Missing downstream skills should produce recommendations and fallback guidance, not a hard stop.

## CLI

Use `scripts/router_modules.py` for read-only inspection:

```bash
python3 scripts/router_modules.py list
python3 scripts/router_modules.py validate
python3 scripts/router_modules.py plan "fix the React dashboard and add browser verification"
python3 scripts/router_modules.py plan-json "fix the React dashboard and add browser verification"
```

`validate` checks router modules and their pipeline registry structure. It does not require recommended downstream skills to be installed.

Use `scripts/evaluate_routes.py` from the repository root to run routing regression evals against the full matrix.

## Common Mistakes

- Hard-coding one user's skill paths into public registries.
- Treating recommended downstream skills as required dependencies.
- Loading both domain routers for a simple task.
- Putting content or coding execution logic in this main router.
- Failing when a recommended downstream skill is missing instead of recommending it.
