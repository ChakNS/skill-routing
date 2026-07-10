#!/usr/bin/env python3
"""Shared compatibility CLI for content and coding route packs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from routing_core import (
    build_domain_plan,
    empty_profile,
    load_json,
    pipeline_candidates,
    PIPELINE_MIN_SCORE,
    read_profile,
    validate_registry,
)


def emit(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {as_text(item)}" for key, item in value.items())
    return str(value)


def installed_map(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in profile.get("catalog", []) if item.get("enabled", True)}


def list_items(registry: dict[str, Any], profile: dict[str, Any], kind: str) -> None:
    installed = installed_map(profile)
    key = {"skills": "skills", "pipelines": "pipelines", "stages": "stages", "layers": "layers"}[kind]
    for item in registry.get(key, []):
        identifier = item.get("name", item.get("id"))
        if kind == "skills":
            status = "installed" if identifier in installed else "missing"
            print(f"- {identifier} [{status}]: {item.get('use_when', '')}")
        else:
            print(f"- {identifier}: {item.get('label', item.get('purpose', ''))}")


def build_plan(registry: dict[str, Any], profile: dict[str, Any], prompt: str) -> dict[str, Any]:
    module_id = registry.get("router", "").removesuffix("-skill-routing")
    module = {
        "id": module_id,
        "label": registry.get("router", module_id),
        "domains": [module_id],
        "registry": registry,
    }
    candidates = pipeline_candidates([module], prompt)
    if not candidates or candidates[0]["score"] < PIPELINE_MIN_SCORE:
        return {
            "router": registry.get("router"),
            "prompt": prompt,
            "matched": False,
            "message": "No pipeline met the confidence threshold.",
        }
    plan, selected = build_domain_plan(candidates[0], profile, prompt)
    plan["prompt"] = prompt
    plan["selected_skills"] = selected
    plan["alternatives"] = [
        {"pipeline": item["pipeline"]["id"], "score": item["score"]}
        for item in candidates[1:4]
    ]
    return plan


def main(registry_path: Path, state_path: Path) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    listing = subparsers.add_parser("list")
    listing.add_argument("kind", choices=["skills", "pipelines", "stages", "layers"])
    search = subparsers.add_parser("search")
    search.add_argument("query")
    explain = subparsers.add_parser("explain")
    explain.add_argument("pipeline_id")
    plan = subparsers.add_parser("plan")
    plan.add_argument("prompt")
    plan_json = subparsers.add_parser("plan-json")
    plan_json.add_argument("prompt")
    subparsers.add_parser("profile")
    subparsers.add_parser("validate")
    args = parser.parse_args()

    registry = load_json(registry_path, {})
    profile = read_profile(state_path) if state_path.exists() else empty_profile()
    if args.command == "list":
        list_items(registry, profile, args.kind)
    elif args.command == "search":
        needle = args.query.casefold()
        matches = []
        for kind in ("skills", "pipelines", "stages"):
            for item in registry.get(kind, []):
                if needle in as_text(item).casefold():
                    matches.append({"kind": kind.removesuffix("s"), "id": item.get("name", item.get("id"))})
        emit(matches)
    elif args.command == "explain":
        pipeline = next((item for item in registry.get("pipelines", []) if item.get("id") == args.pipeline_id), None)
        if pipeline is None:
            raise SystemExit(f"Pipeline not found: {args.pipeline_id}")
        emit(pipeline)
    elif args.command in {"plan", "plan-json"}:
        emit(build_plan(registry, profile, args.prompt))
    elif args.command == "profile":
        emit(
            {
                "state_path": str(state_path),
                "installed_skills": len(profile.get("catalog", [])),
                "bindings": len(profile.get("bindings", {})),
                "resolutions": len(profile.get("resolutions", {})),
            }
        )
    elif args.command == "validate":
        errors = validate_registry(registry, str(registry_path))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            raise SystemExit(1)
        print(
            f"Registry OK: {len(registry.get('skills', []))} skills, "
            f"{len(registry.get('stages', []))} stages, {len(registry.get('pipelines', []))} pipelines."
        )
