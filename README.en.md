# Skill Routing

Language: [中文](README.md) | English

Organize multiple Codex/Claude Skills into a traceable task chain.

Think of this as a workflow router. Given a complex request, it decides which domain router should handle it, breaks the work into stages, maps each stage to candidate skills, and marks which stages can run in parallel.

It is not another writing skill or coding skill. It connects the skills you already have.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

Default target:

```text
~/.codex/skills
```

Validate after installation:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
```

## Try it

Content task:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "prepare a Xiaohongshu note package"
```

Expected shape:

```text
content -> xhs_note_package
step 1: intake
step 2: title_hook + visual_direction in parallel
step 3: draft + asset_generation in parallel
step 4: voice_polish
step 5: handoff
```

Coding task:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan "fix this failing React test and verify browser behavior"
```

Machine-readable output:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py plan-json "prepare a Xiaohongshu note package"
```

## Who should use it

Use it if:

- you already have many skills and need a stable way to compose them
- your tasks often cross stages such as research, writing, visuals, and handoff
- you want the agent to explain which stages and skills were used
- you are building a reusable internal skill/workflow system

Skip it if:

- the task is a small rewrite, quick answer, or tiny one-file edit
- you only need native one-step skill triggering
- the task has no repeatable workflow shape

The value is not "skill detection" by itself. Many agents can already trigger one skill. The value is organizing multiple skills into a traceable task chain.

## Included routers

- `skill-routing`: main router. Dispatches to the right domain router.
- `content-skill-routing`: content, writing, creator workflows, visual packaging, and manual publishing handoff.
- `coding-skill-routing`: coding, debugging, testing, frontend, backend, deployment, GitHub, and skill development.

### Content router handles

- Xiaohongshu/Rednote note packages
- LinkedIn posts
- articles, newsletters, scripts
- titles, hooks, topic planning
- covers, cards, thumbnails, screenshots
- content systems and analytics reviews

### Coding router handles

- bug fixes
- feature work
- UI changes
- tests
- API debugging
- backend/database changes
- skill/plugin maintenance
- PR, commit, and deployment preparation

## How routing works

Each domain router organizes work like this:

```text
layer -> stage -> candidate skill -> execution metadata -> report
```

In practice:

- `layer`: broad category, such as evidence, creation, packaging, build, or quality
- `stage`: small task phase, such as research, draft, asset_generation, or test_authoring
- `candidate skill`: recommended skills for that stage
- `execution metadata`: serial/parallel, dependencies, and agent role
- `report`: how the process should be summarized

Recommended report shape:

```text
stage -> selected skill or fallback -> execution -> evidence/gate -> status
```

## Install options

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

If you fork this repo:

```bash
curl -fsSL https://raw.githubusercontent.com/your-name/skill-routing/main/scripts/install.sh | \
  ROUTING_SKILLS_REPO=your-name/skill-routing \
  bash
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

Downstream skills are soft dependencies. If a recommended skill is missing, the router marks it as a recommendation instead of failing.

## Add your own scenario package

You can add domain routers such as:

- `design-skill-routing`
- `marketing-skill-routing`
- `research-skill-routing`
- `ops-skill-routing`

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

The important file is `pipeline-registry.json`:

```json
{
  "layers": [],
  "stages": [],
  "skills": [],
  "pipelines": []
}
```

A pipeline stage can declare:

- `step`: execution step
- `stage`: stage name
- `candidate_skills`: candidate skills
- `execution`: `serial` or `parallel`
- `parallel_group`: parallel group name
- `depends_on`: upstream stages
- `agent_role`: role of the agent handling this stage

Then register the new router in:

```text
skill-routing/references/router-modules.json
```

## Local validation

If you cloned the repository:

```bash
python3 scripts/smoke_test.py
python3 scripts/evaluate_routes.py
```

Validate installed routers:

```bash
python3 ~/.codex/skills/skill-routing/scripts/router_modules.py validate
python3 ~/.codex/skills/content-skill-routing/scripts/router_registry.py validate
python3 ~/.codex/skills/coding-skill-routing/scripts/router_registry.py validate
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

## Boundaries

- This is a routing matrix, not a full executor.
- It plans chains, prints structured plans, and validates routing rules.
- Actual execution still happens through the agent and downstream skills.
- The content router prepares publishing materials only. It does not log in, publish, like, comment, or message.

## License

MIT. See [LICENSE](LICENSE).
