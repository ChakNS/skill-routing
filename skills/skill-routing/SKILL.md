---
name: skill-routing
description: Use first when a user with many installed skills needs the best local skill or a staged skill chain selected; when initializing, refreshing, auditing, or personalizing a local skill catalog; or when resolving missing-skill installation, replacement, fallback, or disabled-node decisions. Also use for routing conflicts, custom route packs, and routing evals. Skip when the user already selected a skill and no routing decision remains.
compatibility: Requires Python 3.10+ and filesystem access to the skill directories the user chooses to scan.
---

# Skill Routing

## Core contract

Turn the user's installed skills into a personal routing catalog, then select the smallest useful skill set for the current task. Content and coding packs are optional route templates; installed local skills are first-class candidates even when their names do not appear in a pack.

This skill is a control plane, not a substitute for downstream skills. After selecting a skill, read that skill's `SKILL.md` and use it to perform the stage. Never claim a stage succeeded merely because a route was generated.

## Honest platform boundary

- Codex: invoke with `$skill-routing`, for example `$skill-routing init`.
- Claude Code: invoke with `/skill-routing`, for example `/skill-routing init`.
- Do not claim `/init`. Both hosts reserve that command for project instruction scaffolding.
- Implicit activation is host/model behavior. With very large skill collections, explicit invocation is the reliable entry point.

## Locate the CLI

Resolve paths relative to this skill directory, then use:

```bash
python3 <skill-routing-dir>/scripts/router_modules.py <command>
```

Mutable state defaults to `<installed-skills-root>/.skill-routing/profile.json`, outside replaceable package directories. Set `SKILL_ROUTING_STATE` or pass `--state` to share or relocate it.

## First run and refresh

When the user says `init`, or when routing state is absent:

1. Run `init`. Add explicit `--scan-root` values the user supplied. Do not invent directories.
2. Report discovered skills, duplicate-name conflicts, warnings, and route packs.
3. If conflicts could change selection, show the selected path and alternatives. Do not silently delete either copy.
4. Explain that discovery reads bounded frontmatter only; it never executes discovered scripts or inline commands.

Use `refresh` after a skill is installed, removed, moved, or edited. Refresh preserves bindings, missing-skill decisions, and feedback.

## Route and execute

For a normal task:

1. Run `plan-json "<task>"`.
2. Respect the result type:
   - `direct`: load the single selected local skill and execute it.
   - `pipeline`: execute stages in dependency order, loading only each stage's selected skill.
   - `composed_pipeline`: keep content and coding branches separate until their declared merge/handoff.
   - `management`: stay in this skill and use its management commands.
   - `abstain`: clarify the deliverable or proceed without claiming a specialized route.
3. Treat `confidence` as a routing signal, not a probability of task success. If the top route is low-confidence or the alternatives would materially change the artifact, ask one clarifying question.
4. Follow host permissions and project instructions. A route never grants permission for deployment, publishing, credentials, migrations, or other external writes.

## Missing skill decision loop

The CLI first checks installed candidates, user replacements, manual bindings, and safe local capability fallbacks. If a stage returns `decision_required`:

1. Consolidate related missing stages into one concise question.
2. Offer only these choices:
   - install from a user-approved, trusted source;
   - replace with an installed skill;
   - use the host agent's general fallback;
   - disable the route node.
3. Never execute an `install_hint`; it is descriptive text, not a command or trusted source manifest.
4. Install only after explicit approval. Use the host's trusted installer, then run `refresh` and re-plan the same task.
5. If the user declines, persist the chosen behavior with `resolve`, then re-plan. Do not repeatedly ask for the same node.
6. Disabling a node changes the plan, not reality. If the removed node was necessary for the requested artifact, disclose the degraded or blocked result.

Examples:

```bash
python3 <dir>/scripts/router_modules.py resolve \
  --module content --stage title_hook --skill hook-generator \
  --action replace --replacement my-local-title-skill

python3 <dir>/scripts/router_modules.py resolve \
  --module content --stage title_hook --skill hook-generator \
  --action fallback
```

## Personalization

- Use `bind --module <id> --stage <id> --skill <installed-name>` for an explicit stage preference.
- After verified execution, record `feedback --skill <name> --outcome success|failure`.
- Feedback may reorder equivalent candidates. It must never weaken permissions, safety gates, or explicit user choices.
- Prompt text is not persisted by default; feedback stores a short hash for correlation.
- Use `resolve ... --action clear` to reset one missing-skill decision, or rerun `init` to rebuild automatic bindings.

## Commands

```bash
python3 <dir>/scripts/router_modules.py init
python3 <dir>/scripts/router_modules.py refresh
python3 <dir>/scripts/router_modules.py inventory --conflicts
python3 <dir>/scripts/router_modules.py plan-json "<task>"
python3 <dir>/scripts/router_modules.py bind --module <module> --stage <stage> --skill <name>
python3 <dir>/scripts/router_modules.py resolve --module <module> --stage <stage> --skill <name> --action <replace|fallback|disable|clear>
python3 <dir>/scripts/router_modules.py feedback --skill <name> --outcome <success|failure>
python3 <dir>/scripts/router_modules.py doctor
python3 <dir>/scripts/router_modules.py validate
```

## Completion report

For multi-stage work, report only material decisions:

`stage -> selected skill or fallback -> evidence/gate -> status`

Include unresolved decisions, disabled required nodes, degraded output, and verification evidence. Do not list every candidate considered.

## Limitations

- This router improves deterministic discovery and candidate selection; it cannot guarantee perfect semantic matching.
- It can discover filesystem skills in configured roots, not hidden host/system capabilities that have no readable skill artifact.
- It does not install arbitrary internet code, execute downstream skills by itself, or bypass host skill-list/context limits.
