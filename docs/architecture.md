# Architecture and Product Boundary

Skill Routing is a local control plane for Agent Skills. It inventories readable `SKILL.md` files, builds a personal overlay, chooses either a direct installed skill or a route-pack pipeline, and records user decisions. The host agent still reads and executes selected downstream skills.

## Why this is not prompt-only

A prompt-only router cannot safely recurse through local directories, detect stale paths, preserve decisions across sessions, or update state atomically. It also cannot guarantee that a host will activate it when the host truncates a very large skill list. The repository therefore separates responsibilities:

```text
Host skill invocation
        |
        v
skill-routing/SKILL.md       conversation and permission policy
        |
        v
router_modules.py            stable CLI and JSON contract
        |
        v
routing_core.py              discovery, matching, resolution, state
        |
        +--> personal profile (mutable)
        +--> content/coding route packs (immutable templates)
```

## Lifecycle

1. `init` recursively scans configured roots for bounded `SKILL.md` frontmatter. It does not import a skill or execute bundled commands.
2. The catalog retains one effective variant per name and reports all duplicate paths.
3. Automatic stage bindings are generated from skill name/description metadata. Manual bindings and prior decisions are preserved.
4. `plan-json` classifies a request as `direct`, `pipeline`, `composed_pipeline`, `management`, or `abstain`.
5. Each pipeline stage resolves to an installed candidate, a remembered replacement, a local fallback, `decision_required`, `agent_fallback`, or `disabled`.
6. The host loads only selected downstream skills and executes them under normal host permissions.
7. Verified success/failure feedback can reorder equivalent local candidates without changing safety or authorization.

## Matching model

The default matcher is deterministic and offline:

- Unicode-aware word and CJK n-gram retrieval;
- a small bilingual concept bridge for common content/coding terms;
- word-boundary phrase matching to avoid cases such as `capital` matching `api`;
- required and excluded route-pack phrases;
- negation checks for conditional actions;
- installed-skill metadata, explicit bindings, remembered replacements, and bounded feedback boosts;
- confidence thresholds and abstention instead of accepting any positive substring.

This is intentionally not marketed as perfect semantic search. An embedding or model reranker can be added later as an optional adapter, but the deterministic core remains the reproducible baseline and fallback.

## Immutable packs, mutable overlay

Content and coding registries are templates. They describe stages, dependencies, conditional recommended skills, and execution boundaries. They do not own the user's catalog or preferences.

Mutable data lives in `.skill-routing/profile.json` next to the selected install root. Package replacement does not overwrite it. The profile stores absolute local paths because it is machine-local; public route-pack registries use relative paths.

See these bundled contracts:

- `skills/skill-routing/references/profile.schema.json`
- `skills/skill-routing/references/route-pack.schema.json`

## Installation decisions

A missing skill recommendation is not an install manifest. The router may present `install_hint` text, but it never executes it. Installation requires:

1. a user-approved source and installer;
2. normal host permissions;
3. refresh after installation;
4. re-planning the current request.

If the user declines, `resolve` persists a replacement, general fallback, or disabled node. Required output that no remaining capability can produce must be reported as degraded or blocked by the host; deleting a node does not create the capability.

## Host-specific invocation

- Codex: `$skill-routing init` or `$skill-routing <task>`.
- Claude Code: `/skill-routing init` or `/skill-routing <task>`.

The project does not replace `/init`; that name is reserved by both hosts. Codex-specific UI metadata lives in `agents/openai.yaml`. The portable `SKILL.md` and Python CLI remain the source of behavior.

## Security and privacy

- Discovery reads at most 256 KiB per `SKILL.md` and skips common dependency/cache trees.
- Discovered scripts and dynamic shell snippets are never executed during scan or match.
- State and package writes use same-directory temporary files and atomic replacement.
- Installer and state writes use lock files with stale-lock recovery.
- Installer rejects targets inside or around the source tree, stages packages before replacement, backs up replaced packages, and restores them if a later step fails.
- Feedback stores a short prompt hash, not prompt text.
- Routing never grants external-write authority.

## Known limitations

- Only readable filesystem skills in configured roots are indexed. Hidden system capabilities and remote plugin tools may be invisible.
- Duplicate precedence follows scan-root order, not every host's full enterprise/project precedence model; conflicts are surfaced for manual correction.
- JSON state is designed for short CLI transactions, not high-throughput concurrent services.
- Bash one-line installation targets macOS/Linux. The Python installer is the portable entry point for Windows.
- The project plans and resolves stages; it does not implement a standalone agent executor.
