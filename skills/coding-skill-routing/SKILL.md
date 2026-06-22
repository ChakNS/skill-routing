---
name: coding-skill-routing
description: Use when a software request needs a staged, traceable chain across codebase context, design, implementation, debugging, testing, browser verification, release, or skill/plugin development. Good fits include feature work, bug fixes, UI changes, backend/data changes, OpenAI API work, and skill development. Do not use it merely to pick one coding skill for a tiny edit.
---

# Coding Skill Routing

## Purpose

Use this router before multi-stage software engineering work. It turns a broad coding request into a traceable chain of stages, candidate skills, dependencies, parallel groups, and verification gates.

This is an open-source router. Its public registry contains layered skill categories, stage definitions, recommended skill trees, and execution metadata. Installation may generate `references/local-skill-profile.generated.json` to mark which recommended skills are already present on the user's machine.

## Load Order

1. Read this file.
2. For simple questions or tiny edits, use this file alone unless the route is ambiguous.
3. For non-trivial work, read only the matching section in `references/route-tables.md`.
4. For multi-stage work, read `references/pipeline-registry.json` to choose a layered stage-by-stage pipeline.
5. If present, read `references/local-skill-profile.generated.json` to know which recommended skills are installed.
6. Load selected downstream skills only when installed and when their stage is about to execute.

If a recommended downstream skill is missing, state the recommendation and continue with the best available general engineering workflow.

## Complexity Gate

Use this router when the task crosses at least two meaningful stages, such as context scan -> implementation -> verification, debugging -> fix -> regression test, or design -> browser verification -> visual QA.

Skip this router for tiny one-file edits, simple questions, or obvious single-skill operations unless the user asks for routing traceability. In those cases, inspect the code and use the relevant downstream skill directly.

## Orchestration Model

Use the clarification gate only when the missing answer changes the route, implementation boundary, verification method, or final artifact. Do not ask for routine preferences when codebase evidence can answer them.

Ask before routing when:

- The deliverable, repository, failure symptom, acceptance condition, or deployment target is unclear.
- The request could mean materially different workflows.
- A write operation, production system, database migration, deployment, PR merge, or credential action is implied but not explicit.

Do not ask before routing when:

- The user gives a concrete file, bug, failing command, feature, or visible acceptance condition.
- Existing project files can safely resolve framework, test, or build choices.
- The uncertainty affects only implementation style; inspect similar code and continue.

## Pipeline Decomposition

For sequential work, decompose into stages such as `intake`, `context_scan`, `design`, `plan`, `implementation`, `debugging`, `test_authoring`, `browser_verification`, `visual_qa`, `security_review`, `release`, and `handoff`.

Use registry layers to explain why each skill is selected:

- `intake`: clarify repository, acceptance criteria, risk boundaries, and write permissions.
- `intelligence`: inspect project rules, architecture, dependency paths, and impact areas.
- `design`: choose architecture, UX, API, data, or skill design before writing.
- `build`: modify code, tests, docs, scripts, registries, and configuration.
- `quality`: run tests, browser checks, visual QA, security review, and verification.
- `release`: prepare handoff, commits, PRs, CI checks, deployment, and rollback notes.

Do not load every recommended skill in a pipeline upfront. Select the current stage, check the generated local profile, then either load an installed skill or recommend a missing one.

## Parallel Agent Routing

When `pipeline-registry.json` marks multiple stages with the same `step` and `parallel_group`, prefer separate agents for independent branches. Examples: design and acceptance-test planning, implementation and regression-test authoring, browser verification and visual QA, or skill editing and smoke-test updates.

Do not parallelize branches that edit the same files without a merge plan, share mutable state, require a single external session, or depend on unresolved root-cause evidence. Merge branch outputs in the next serial stage and keep the final verification stage responsible for the integrated result.

## Gates

- Inspect existing project rules and patterns first.
- Respect dirty worktrees; never revert user changes unless explicitly asked.
- Prefer root-cause evidence over speculative fixes.
- Verify before claiming fixed, passing, deployed, or ready.
- External writes require explicit user intent: deploys, PR creation, PR merge, database migrations, cloud changes, and credential actions.
- Version-sensitive OpenAI/API/framework questions should use current official documentation.

## Routing Report

For multi-stage work, finish with a compact report:

`stage -> selected skill or recommendation -> reason -> evidence/gate -> status`

Mention missing recommended skills only when they would materially improve the result.
For parallel groups, include the group name, branch agent roles, and how the branch outputs were merged.

## CLI

Use `scripts/router_registry.py` for read-only inspection:

```bash
python3 scripts/router_registry.py list skills
python3 scripts/router_registry.py list pipelines
python3 scripts/router_registry.py plan "fix this failing React test and verify it in browser"
python3 scripts/router_registry.py plan-json "fix this failing React test and verify it in browser"
python3 scripts/router_registry.py validate
```

## Public References

- `references/pipeline-registry.json`: structured stage, skill, and pipeline recommendations.
- `references/route-tables.md`: route notes by engineering domain.
- `references/routing-fixtures.md`: regression examples.
- `references/local-skill-profile.generated.json`: optional generated local capability map.

## Common Mistakes

- Treating routing as implementation.
- Loading broad method packs when project inspection is enough.
- Implementing before goal, reproduction, or acceptance signal is checkable.
- Claiming completion without fresh verification.
- Failing when a recommended downstream skill is missing.
- Recommending a local-only skill as mandatory public behavior.
