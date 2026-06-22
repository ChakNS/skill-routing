# Skill Routing

Language: [中文](README.md) | English

This repository provides a workflow routing matrix for Codex/Claude Skills. It does not replace downstream skills, and it does not pretend to be smarter than native skill triggering for simple one-step tasks. It handles a different problem: turning a complex request into a traceable chain of stages, candidate skills, dependencies, parallel branches, and final reporting.

If you already have many skills installed, the problem is usually not a lack of tools. The harder problem is orchestration. A model may know many skills exist, but still choose the wrong one first, skip an evidence step, or forget to merge parallel outputs. This project handles that routing layer.

## What it solves

Most skills are standalone. A writing skill writes. A screenshot skill captures. A debugging skill debugs. Real tasks are rarely that clean.

For example, "prepare a Xiaohongshu/Rednote note package" may involve:

- clarifying the topic, platform, and source material
- generating titles and hooks
- drafting body copy
- defining cover direction
- generating or rendering visual assets
- preparing a manual publishing checklist

Some stages must be sequential. Others can run in parallel. Title exploration and cover direction can happen at the same time. Body copy and asset generation may also run in parallel. The final handoff stage merges copy, tags, assets, and manual publishing notes.

This router does four things:

1. Breaks large tasks into smaller stages.
2. Matches each stage with candidate skills.
3. Marks which stages should run serially and which can run in parallel.
4. Produces a clear routing chain instead of a vague recommendation.

It is not a full execution engine. The current version plans, validates, and explains task chains. Actual execution still happens through the agent or downstream skills.

## Features

- Layered routing: domain, layer, stage, then skill.
- Pluggable modules: ships with `content-skill-routing` and `coding-skill-routing`; more domain routers can be added later.
- Local skill scan: installation generates `local-skill-profile.generated.json` from the user's existing skills.
- Soft dependencies: missing downstream skills are treated as recommendations, not fatal errors.
- Parallel stage metadata: registries can declare `parallel_group` for multi-agent execution.
- Traceable output: CLI planning shows layers, dependencies, candidate skills, agent roles, and report templates.
- Machine-readable plans: `plan-json` prints structured routing output for UIs, evals, or a future executor.
- Routing regression evals: included evals check expected modules, pipelines, stages, and parallel groups.
- Manual publishing boundary: the content router prepares assets and handoff packages, but does not log in, post, like, comment, or publish.

## When to use it

Use it when:

- a task clearly spans multiple stages, such as research, writing, visuals, and handoff
- the local environment has many skills and needs a stable composition layer
- a team wants to audit why an agent selected a chain of skills
- you want to preserve a repeatable workflow for content packages, UI changes, bug fixes, or skill development

Do not use it when:

- the task is a small rewrite, quick answer, or tiny one-file edit
- all you need is native skill triggering
- the task has no repeatable workflow shape

The value is not "skill detection" by itself. The value is organizing multiple skills into a traceable task chain.

## Included routers

### `skill-routing`

The main router. It chooses the right domain router for a task.

Example:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "prepare a Xiaohongshu note package"
```

This dispatches to `content-skill-routing`.

### `content-skill-routing`

For content creation, writing, creator operations, visual packaging, and manual publish handoff.

Good fits:

- Xiaohongshu/Rednote note packages
- LinkedIn posts
- articles, newsletters, scripts
- titles, hooks, topic planning
- covers, cards, thumbnails, screenshots
- content systems, topic libraries, analytics reviews

### `coding-skill-routing`

For software engineering, debugging, testing, frontend, backend, deployment, GitHub, and skill development.

Good fits:

- fixing bugs
- building features
- improving UI
- writing tests
- debugging APIs
- changing backend or database behavior
- creating or maintaining skills/plugins
- preparing commits, PRs, and deployments

## Routing model

Domain routers organize work like this:

```text
layer -> stage -> candidate skill -> execution metadata -> report line
```

For a Xiaohongshu note package, the route may look like this:

```text
step 1: intake
step 2: title_hook + visual_direction in parallel
step 3: draft + asset_generation in parallel
step 4: voice_polish
step 5: handoff
```

The CLI prints:

- the layer for each stage
- whether the stage is serial or parallel
- stage dependencies
- recommended candidate skills
- the agent role for each stage
- the report format expected at the end

For machine-readable output:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan-json "prepare a Xiaohongshu note package"
```

Recommended final report shape:

```text
stage -> selected skill or fallback -> execution -> evidence/gate -> status
```

## Scenario package model

This project is designed to grow by adding scenario packages, not by stuffing every rule into one giant `SKILL.md`.

A scenario package usually looks like this:

```text
your-router/
├── SKILL.md
├── references/
│   ├── pipeline-registry.json
│   ├── route-tables.md
│   └── routing-fixtures.md
└── scripts/
    └── router_registry.py
```

To add a new scenario package:

1. Create a domain router, such as `design-skill-routing` or `marketing-skill-routing`.
2. Define layers, stages, skills, and pipelines in `pipeline-registry.json`.
3. Register the router in `skill-routing/references/router-modules.json`.

Recommended registry shape:

```json
{
  "layers": [],
  "stages": [],
  "skills": [],
  "pipelines": []
}
```

Pipeline stages may include:

- `step`: execution step
- `stage`: stage name
- `candidate_skills`: candidate downstream skills
- `execution`: `serial` or `parallel`
- `parallel_group`: parallel group name
- `depends_on`: upstream stages
- `agent_role`: the role of the agent handling this stage

This is the core pattern: split a large task into small stages, then chain skills across those stages.

## Installation

After publishing this repository to GitHub, users can install it with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

If you fork this repository, set `ROUTING_SKILLS_REPO` to your own repository.

Default install target:

```text
~/.codex/skills
```

Install only the main router and content router:

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_MODULES=main,content \
  bash
```

Set a custom target:

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_TARGET=~/.codex/skills \
  bash
```

Set extra scan roots:

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_SCAN_ROOT=~/my-skills:~/team-skills \
  bash
```

For local development:

```bash
python3 scripts/install.py --target ~/.codex/skills --modules all
```

## What the installer does

The installer:

1. Copies selected router skills into the target skill directory.
2. Scans existing `SKILL.md` files.
3. Writes `skill-routing/references/router-modules.json`.
4. Writes `local-skill-profile.generated.json` for each installed domain router.

Default scan roots:

```text
~/.codex/skills
~/.claude/skills
~/.cc-switch/skills
~/AISkills
```

## Validation

From the repository root:

```bash
python3 scripts/smoke_test.py
```

Run only routing regression evals:

```bash
python3 scripts/evaluate_routes.py
```

The eval cases live in `evals/routing-evals.json`. They check:

- expected module
- expected pipeline
- required stages
- required parallel groups

Validate installed routers:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py validate
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py validate
```

Try planning:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "prepare a Xiaohongshu note package"
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py plan "write a LinkedIn post from notes and prepare a manual publish package"
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py plan "improve this skill installer and add tests"
```

## Directory layout

```text
skill-routing/
├── LICENSE
├── README.md
├── README.en.md
├── evals/
│   └── routing-evals.json
├── scripts/
│   ├── evaluate_routes.py
│   ├── install.py
│   ├── install.sh
│   └── smoke_test.py
└── skills/
    ├── skill-routing/
    ├── content-skill-routing/
    └── coding-skill-routing/
```

## Release checklist

1. Run `python3 scripts/smoke_test.py`.
2. If publishing a fork, confirm the default repository name in README and `scripts/install.sh`.
3. Install into a temporary directory and inspect generated profiles.
4. Confirm the Chinese and English README files describe the same install flow.

## License

MIT. See [LICENSE](LICENSE).
