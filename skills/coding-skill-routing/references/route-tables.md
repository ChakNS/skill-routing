# Coding Route Tables

Use this file only after `coding-skill-routing/SKILL.md` identifies a non-trivial software task.

## Implementation

Use for feature work, integrations, refactors, and code changes.

Default route:

1. `context_scan`
2. `plan` when the change crosses multiple files or contracts.
3. `implementation`
4. `test_authoring`
5. `handoff`

Recommended downstream skills are optional. If missing, inspect code directly and continue.

## Debugging

Use for bugs, failing tests, runtime errors, regressions, and performance symptoms.

Default route:

1. `debugging`
2. `implementation`
3. `test_authoring`
4. `handoff`

Root-cause evidence is required before claiming a fix.

## Frontend / UI

Use for React, Vue, CSS, components, responsive layout, visual design, and browser behavior.

Default route:

1. `context_scan`
2. `design`
3. `implementation`
4. `browser_verification`
5. `visual_qa`

Screenshots or browser checks are preferred before completion.

## Backend / Data

Use for APIs, services, auth, databases, migrations, queues, Postgres, and Supabase.

Default route:

1. `context_scan`
2. `design`
3. `implementation`
4. `test_authoring`
5. `handoff`

Database writes, migrations, and cloud changes need explicit user intent.

## Skill Tooling

Use for creating, editing, testing, packaging, or publishing skills and plugins.

Default route:

1. `design`
2. `implementation`
3. `test_authoring`
4. `handoff`

Skill creation should include realistic test prompts and a validation path.

## Release

Use for commits, PRs, CI, deployment, release notes, and rollback notes.

Default route:

1. `handoff` verification
2. `release`

External writes require explicit user intent.
