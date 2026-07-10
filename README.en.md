# Skill Routing

Language: [中文](README.md) | English

Skill Routing helps your agent organize and use the skills installed on your machine.

The problem appears once you have many Codex or Claude skills installed. Names overlap. Descriptions sound similar. Two skills may share the same name. A single request may need several skills in sequence. At that point, the agent can easily miss the best local skill or pick one that is only loosely related.

Skill Routing sits one layer above your skills. It scans local `SKILL.md` files, builds a personal routing profile, then helps the agent choose one installed skill or a staged route pack such as content creation or coding. Replacements, fallbacks, disabled nodes, conflicts, and feedback are stored locally, so the router adapts to your setup over time.

It is not another writing skill or coding skill. Think of it as a local dispatch desk for your skills.

## How to use it

The friendliest way is to ask your agent directly:

```text
Use skill-routing to turn this technical article into a Xiaohongshu post package and generate a cover.
```

For first-time setup, tell your agent:

```text
Install this skill-routing skill:
https://github.com/ChakNS/skill-routing

After installation, initialize it and organize my local skills.
```

If your host supports explicit skill invocation:

```text
$skill-routing init
```

In Claude Code, this is usually:

```text
/skill-routing init
```

Do not use `/init` for this project. Host tools commonly reserve that command.

## When it helps

Use it when:

- You have many local skills and do not always know which one fits.
- You want the first run to inventory your installed skills automatically.
- You want to use content or coding route packs without installing every recommended downstream skill.
- You want missing skills to be installed, replaced with local skills, skipped, or handled by the base agent.
- You want those choices remembered in a personal routing profile.

Skip it when:

- You only have one or two skills.
- The request is a simple answer or small rewrite.
- You want automatic installation of untrusted code.
- You need a full execution engine instead of skill matching and routing.

## What happens on first run

During initialization, Skill Routing scans common local skill directories such as:

- `~/.agents/skills`
- `~/.claude/skills`
- `~/.codex/skills`
- `~/AISkills`

It reads `SKILL.md` descriptions and metadata. It does not execute scripts from discovered skills.

The generated local profile records installed skills, duplicate names, trusted paths, route-pack decisions, missing-skill choices, and feedback. Package updates should not overwrite your personal choices.

## How routing behaves

Skill Routing tries to return an explainable decision:

- `direct`: use one installed skill.
- `pipeline`: use a staged route pack.
- `composed_pipeline`: combine domains, such as coding plus launch content.
- `management`: handle initialization, refresh, inventory, or conflict resolution.
- `abstain`: do not force a match when the evidence is weak.

For example:

```text
Use skill-routing to turn this technical article into a Xiaohongshu post package and generate a cover.
```

The router may break the work into reading the source, rewriting the post, generating title directions, planning the cover, and handing off the result. Each stage prefers skills already installed locally. If a recommended skill is missing, the router asks how you want to handle it.

## Missing skills

Route-pack candidates are recommendations, not hard requirements. You do not have to install every skill mentioned by a route pack.

When a skill is missing, ask your agent to choose one of these paths:

```text
I want to install this skill. Show me the source and risk first, then continue.
```

```text
Do not install it. Use a similar skill I already have.
```

```text
This stage can fall back to the general agent.
```

```text
Do not recommend this skill in this route pack again.
```

Skill Routing stores the decision in your local profile.

## Included route packs

- `skill-routing`: initialization, inventory, conflict handling, missing-skill decisions, and main routing.
- `content-skill-routing`: articles, social posts, Xiaohongshu packages, covers, content systems, and creator workflows.
- `coding-skill-routing`: features, bugs, tests, frontend, backend, OpenAI API work, skill/plugin development, and PR preparation.

You can install only the main router, or add the content and coding packs. Missing downstream skills can be handled later.

## Manual installation

Asking your agent to install and initialize the skill is usually easier. If you prefer manual installation:

```bash
git clone https://github.com/ChakNS/skill-routing.git
cd skill-routing
python3 scripts/install.py --target ~/.agents/skills --modules all
```

Claude Code users usually install to:

```bash
python3 scripts/install.py --target ~/.claude/skills --modules all
```

On macOS or Linux, you can use the convenience script after you trust the repository:

```bash
curl -fsSL https://raw.githubusercontent.com/ChakNS/skill-routing/main/scripts/install.sh | bash
```

## Safety boundary

Skill Routing is intentionally conservative.

- It does not execute scripts from scanned skills.
- It does not auto-install unknown code.
- It does not grant external write permissions such as posting, deployment, PR creation, or database migration.
- It cannot guarantee implicit activation by the host agent. In large skill collections, explicitly say "use skill-routing".
- It should abstain rather than pretend to know.

## Custom route packs

You can package your own workflow as a route pack.

Typical structure:

```text
your-skill-routing/
├── SKILL.md
├── references/
│   └── pipeline-registry.json
└── scripts/
    └── router_registry.py
```

Docs:

- [Architecture](docs/architecture.md)
- [Evaluation](docs/evaluation.md)
- [Personal profile schema](skills/skill-routing/references/profile.schema.json)
- [Route pack schema](skills/skill-routing/references/route-pack.schema.json)

## License

MIT. See [LICENSE](LICENSE).
