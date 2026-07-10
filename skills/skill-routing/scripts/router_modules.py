#!/usr/bin/env python3
"""Initialize, inspect, personalize, validate, and plan skill routes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from routing_core import (
    bind_skill,
    canonical,
    default_scan_roots,
    default_state_path,
    initialize_profile,
    load_json,
    load_modules,
    read_profile,
    record_feedback,
    record_conflict_preference,
    record_resolution,
    route_prompt,
    validate_all,
    validate_module_registry_data,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODULES_PATH = ROOT / "references" / "router-modules.json"


def emit(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))


def list_modules(modules_path: Path) -> None:
    data = load_json(modules_path, {"modules": []})
    errors = validate_module_registry_data(data, str(modules_path))
    if errors:
        raise ValueError("; ".join(errors))
    for module in data.get("modules", []):
        status = "enabled" if module.get("enabled", True) else "disabled"
        print(f"- {module.get('id')}: {module.get('label', module.get('id'))} [{status}]")
        print(f"  skill: {module.get('skill_path', '')}")
        print(f"  registry: {module.get('registry_path', '')}")
        print(f"  domains: {', '.join(module.get('domains', []))}")


def init_command(args: argparse.Namespace, state_path: Path, modules_path: Path, *, refresh: bool = False) -> None:
    if args.scan_root:
        explicit = [Path(item) for item in args.scan_root]
    else:
        explicit = []
    if args.no_default_scan_roots:
        roots = explicit
    elif refresh and state_path.exists() and not explicit:
        roots = [Path(item) for item in read_profile(state_path).get("scan_roots", [])]
    else:
        roots = [*default_scan_roots(), *explicit]
    _, summary = initialize_profile(ROOT, modules_path, state_path, roots)
    if args.json:
        emit(summary)
        return
    verb = "Refreshed" if refresh else "Initialized"
    inventory = summary["inventory"]
    print(f"{verb} personal skill routing profile: {summary['state_path']}")
    print(f"- effective skills: {inventory['effective_skills']}")
    print(f"- discovered variants: {inventory['variants']}")
    print(f"- duplicate-name conflicts: {inventory['conflicts']}")
    print(f"- route packs: {', '.join(summary['route_packs']) or 'none'}")
    print("Use `inventory --conflicts`, then `plan-json <task>` to inspect decisions.")


def inventory_command(args: argparse.Namespace, state_path: Path) -> None:
    profile = read_profile(state_path)
    if args.conflicts:
        data: Any = profile.get("conflicts", [])
    else:
        data = {
            "state_path": str(state_path),
            "updated_at": profile.get("updated_at"),
            "scan_roots": profile.get("scan_roots", []),
            "skills": profile.get("catalog", []),
            "conflicts": profile.get("conflicts", []),
            "warnings": profile.get("scan_warnings", []),
        }
    if args.json:
        emit(data)
        return
    if args.conflicts:
        if not data:
            print("No duplicate-name conflicts.")
            return
        for conflict in data:
            status = "resolved" if conflict.get("resolved") else "unresolved"
            print(f"- {conflict['name']} [{status}]: selected {conflict['selected_path']}")
            for path in conflict["paths"]:
                print(f"  - {path}")
        return
    print(f"Routing state: {state_path}")
    print(f"Skills: {len(data['skills'])}; conflicts: {len(data['conflicts'])}; warnings: {len(data['warnings'])}")
    for skill in data["skills"]:
        status = "enabled" if skill.get("enabled", True) else "disabled"
        print(f"- {skill['name']} [{status}] {skill['path']}")


def route_command(args: argparse.Namespace, state_path: Path, modules_path: Path) -> None:
    result = route_prompt(ROOT, modules_path, state_path, args.prompt, args.top_k)
    if args.command == "plan-json":
        emit(result)
        return
    print(f"route_kind: {result.get('route_kind')}")
    if result.get("recommended_module"):
        print(f"module: {result['recommended_module']}")
    if result.get("recommended_modules"):
        print(f"modules: {', '.join(result['recommended_modules'])}")
    plan = result.get("domain_plan")
    if plan:
        print(f"pipeline: {plan.get('recommended_pipeline')}")
        for group in plan.get("steps", []):
            stages = ", ".join(stage.get("stage", "") for stage in group.get("stages", []))
            print(f"step {group.get('step')}: {stages}")
    for skill in result.get("selected_skills", []):
        print(f"skill: {skill.get('name')} ({skill.get('reason', 'selected')})")
    if not result.get("matched"):
        print(result.get("message", "No route matched."))
    if result.get("route_kind") == "management":
        print(result.get("message", "Use router management commands."))
    if result.get("route_kind") in {"pipeline", "composed_pipeline"}:
        print("Use `plan-json` for the full machine-readable contract.")


def doctor_command(state_path: Path, modules_path: Path) -> None:
    validation = validate_all(ROOT, modules_path, state_path)
    profile = read_profile(state_path)
    result = {
        **validation,
        "initialized": state_path.exists(),
        "effective_skills": len(profile.get("catalog", [])),
        "conflicts": len(profile.get("conflicts", [])),
        "unresolved_conflicts": sum(1 for item in profile.get("conflicts", []) if not item.get("resolved", False)),
        "scan_warnings": profile.get("scan_warnings", []),
        "resolutions": len(profile.get("resolutions", {})),
        "feedback_skills": len(profile.get("feedback", {})),
    }
    emit(result)
    if not validation["ok"]:
        raise SystemExit(1)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--state", help="Personal profile path. Defaults to <skills-root>/.skill-routing/profile.json.")
    result.add_argument("--modules-file", default=str(DEFAULT_MODULES_PATH), help="Router module registry path.")
    subparsers = result.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List registered route packs.")

    for command, help_text in (("init", "Discover local skills and create a personal routing profile."), ("refresh", "Rescan skills while preserving choices and feedback.")):
        item = subparsers.add_parser(command, help=help_text)
        item.add_argument("--scan-root", action="append", default=[], help="Additional skill root; repeat for multiple roots.")
        item.add_argument("--no-default-scan-roots", action="store_true", help="Scan only explicit --scan-root paths.")
        item.add_argument("--json", action="store_true", help="Print a machine-readable summary.")

    inventory = subparsers.add_parser("inventory", help="Inspect discovered local skills and conflicts.")
    inventory.add_argument("--json", action="store_true")
    inventory.add_argument("--conflicts", action="store_true")

    for command, help_text in (("plan", "Resolve a prompt to a direct skill or staged pipeline."), ("plan-json", "Resolve a prompt and print the stable JSON contract.")):
        item = subparsers.add_parser(command, help=help_text)
        item.add_argument("prompt")
        item.add_argument("--top-k", type=int, default=3)

    bind = subparsers.add_parser("bind", help="Prefer an installed skill for one route-pack stage.")
    bind.add_argument("--module", required=True)
    bind.add_argument("--stage", required=True)
    bind.add_argument("--skill", required=True)

    conflict = subparsers.add_parser("resolve-conflict", help="Choose the trusted path for a duplicate skill name and refresh.")
    conflict.add_argument("--skill", required=True)
    conflict.add_argument("--path", required=True)

    resolve = subparsers.add_parser("resolve", help="Persist a missing-skill replacement, fallback, disabled node, or reset.")
    resolve.add_argument("--module", required=True)
    resolve.add_argument("--stage", required=True)
    resolve.add_argument("--skill", required=True)
    resolve.add_argument("--action", required=True, choices=["replace", "fallback", "disable", "clear"])
    resolve.add_argument("--replacement")

    feedback = subparsers.add_parser("feedback", help="Record local success/failure feedback for future ranking.")
    feedback.add_argument("--skill", required=True)
    feedback.add_argument("--outcome", required=True, choices=["success", "failure"])
    feedback.add_argument("--prompt", default="")
    feedback.add_argument("--module", default="")
    feedback.add_argument("--stage", default="")

    subparsers.add_parser("status", help="Show the current personal profile summary.")
    subparsers.add_parser("doctor", help="Diagnose registries, stale catalog entries, and local state.")
    subparsers.add_parser("validate", help="Validate route packs and personal state.")
    return result


def main() -> None:
    args = parser().parse_args()
    modules_path = canonical(Path(args.modules_file))
    state_path = canonical(Path(args.state)) if args.state else default_state_path(ROOT)
    try:
        if args.command == "list":
            list_modules(modules_path)
        elif args.command == "init":
            init_command(args, state_path, modules_path)
        elif args.command == "refresh":
            init_command(args, state_path, modules_path, refresh=True)
        elif args.command == "inventory":
            inventory_command(args, state_path)
        elif args.command in {"plan", "plan-json"}:
            route_command(args, state_path, modules_path)
        elif args.command == "bind":
            modules = load_modules(ROOT, modules_path)
            emit(bind_skill(state_path, modules, args.module, args.stage, args.skill))
        elif args.command == "resolve-conflict":
            result = record_conflict_preference(state_path, args.skill, args.path)
            roots = [Path(item) for item in read_profile(state_path).get("scan_roots", [])]
            _, summary = initialize_profile(ROOT, modules_path, state_path, roots)
            emit({**result, "refreshed": True, "inventory": summary["inventory"]})
        elif args.command == "resolve":
            modules = load_modules(ROOT, modules_path)
            emit(record_resolution(state_path, args.module, args.stage, args.skill, args.action, args.replacement, modules))
        elif args.command == "feedback":
            emit(record_feedback(state_path, args.skill, args.outcome, args.prompt, args.module, args.stage))
        elif args.command == "status":
            profile = read_profile(state_path)
            emit(
                {
                    "initialized": state_path.exists(),
                    "state_path": str(state_path),
                    "updated_at": profile.get("updated_at"),
                    "effective_skills": len(profile.get("catalog", [])),
                    "conflicts": len(profile.get("conflicts", [])),
                    "resolutions": len(profile.get("resolutions", {})),
                    "feedback_skills": len(profile.get("feedback", {})),
                }
            )
        elif args.command == "doctor":
            doctor_command(state_path, modules_path)
        elif args.command == "validate":
            validation = validate_all(ROOT, modules_path, state_path)
            if validation["ok"]:
                print(f"Router modules OK: {validation['modules']} modules. State: {state_path}")
            else:
                for error in validation["errors"]:
                    print(f"ERROR: {error}", file=sys.stderr)
                raise SystemExit(1)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
