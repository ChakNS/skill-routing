#!/usr/bin/env python3
"""Inspect and plan with a domain routing pipeline registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "references" / "pipeline-registry.json"
PROFILE_PATH = ROOT / "references" / "local-skill-profile.generated.json"


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_profile() -> dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {"recommended_skills": []}
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def installed_map(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in profile.get("recommended_skills", [])}


def stage_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in registry.get("stages", [])}


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {as_text(item)}" for key, item in value.items())
    return str(value)


def print_skill(skill: dict[str, Any], profile_items: dict[str, dict[str, Any]]) -> None:
    local = profile_items.get(skill["name"], {})
    status = "installed" if local.get("installed") else "recommendation"
    print(f"- {skill['name']} [{status}]")
    if local.get("installed_path"):
        print(f"  path: {local['installed_path']}")
    print(f"  priority: {skill.get('priority', 'normal')}")
    if skill.get("category"):
        print(f"  category: {skill['category']}")
    if skill.get("layer"):
        print(f"  layer: {skill['layer']}")
    print(f"  parallel_safe: {str(skill.get('parallel_safe', False)).lower()}")
    print(f"  stages: {', '.join(skill.get('stages', []))}")
    print(f"  use: {skill.get('use_when', '')}")


def list_items(registry: dict[str, Any], profile: dict[str, Any], kind: str) -> None:
    profile_items = installed_map(profile)
    if kind == "skills":
        for skill in registry.get("skills", []):
            print_skill(skill, profile_items)
        return
    if kind == "pipelines":
        for pipeline in registry.get("pipelines", []):
            print(f"- {pipeline['id']}: {pipeline.get('label', '')}")
            print(f"  mode: {pipeline.get('mode', 'default')}")
            print(f"  triggers: {', '.join(pipeline.get('triggers', []))}")
        return
    if kind == "stages":
        for stage in registry.get("stages", []):
            print(f"- {stage['id']}: {stage.get('purpose', '')}")
            if stage.get("layer"):
                print(f"  layer: {stage['layer']}")
        return
    if kind == "layers":
        for layer in registry.get("layers", []):
            print(f"- {layer['id']}: {layer.get('label', '')}")
            if layer.get("purpose"):
                print(f"  {layer['purpose']}")
        return
    raise SystemExit(f"Unknown list kind: {kind}")


def search(registry: dict[str, Any], query: str) -> None:
    needle = query.lower()
    matches: list[tuple[str, str, str]] = []
    for skill in registry.get("skills", []):
        if needle in as_text(skill).lower():
            matches.append(("skill", skill["name"], skill.get("use_when", "")))
    for pipeline in registry.get("pipelines", []):
        if needle in as_text(pipeline).lower():
            matches.append(("pipeline", pipeline["id"], pipeline.get("label", "")))
    if not matches:
        print("No matches.")
        return
    for kind, name, note in matches:
        print(f"- {kind}: {name}")
        if note:
            print(f"  {note}")


def explain(registry: dict[str, Any], profile: dict[str, Any], pipeline_id: str) -> None:
    pipeline = next((item for item in registry.get("pipelines", []) if item["id"] == pipeline_id), None)
    if pipeline is None:
        raise SystemExit(f"Pipeline not found: {pipeline_id}")
    profile_items = installed_map(profile)
    print(f"{pipeline['id']}: {pipeline.get('label', '')}")
    print(f"mode: {pipeline.get('mode', 'default')}")
    if pipeline.get("domain"):
        print(f"domain: {pipeline['domain']}")
    print(f"triggers: {', '.join(pipeline.get('triggers', []))}")
    print_stage_plan(registry, profile_items, pipeline)


def score_pipeline(pipeline: dict[str, Any], prompt: str) -> int:
    text = prompt.lower()
    score = 0
    for trigger in pipeline.get("triggers", []):
        if trigger.lower() in text:
            score += 4
    for token in set(text.replace("/", " ").replace("-", " ").split()):
        if len(token) >= 4 and token in as_text(pipeline).lower():
            score += 1
    return score


def select_pipeline(registry: dict[str, Any], prompt: str) -> tuple[int, dict[str, Any], list[tuple[int, dict[str, Any]]]] | None:
    scored = [(score_pipeline(item, prompt), item) for item in registry.get("pipelines", [])]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    return best_score, best, scored[1:4]


def grouped_stages(pipeline: dict[str, Any]) -> list[tuple[int, list[dict[str, Any]]]]:
    groups: dict[int, list[dict[str, Any]]] = {}
    for index, stage in enumerate(pipeline.get("stages", []), start=1):
        step = int(stage.get("step", index))
        groups.setdefault(step, []).append(stage)
    return [(step, groups[step]) for step in sorted(groups)]


def build_plan_data(registry: dict[str, Any], profile: dict[str, Any], prompt: str) -> dict[str, Any]:
    selected = select_pipeline(registry, prompt)
    if selected is None:
        return {
            "router": registry.get("router"),
            "prompt": prompt,
            "matched": False,
            "message": "No confident pipeline match. Use the router clarification gate before selecting skills.",
        }

    best_score, best, alternatives = selected
    stages = stage_map(registry)
    profile_items = installed_map(profile)
    steps = []
    for step, entries in grouped_stages(best):
        parallel = len(entries) > 1 or any(item.get("execution") == "parallel" for item in entries)
        stage_entries = []
        for item in entries:
            meta = stages.get(item["stage"], {})
            candidates = []
            for skill_name in item.get("candidate_skills", []):
                local = profile_items.get(skill_name, {})
                candidates.append(
                    {
                        "name": skill_name,
                        "status": "installed" if local.get("installed") else "recommendation",
                        "path": local.get("installed_path"),
                    }
                )
            stage_entries.append(
                {
                    "stage": item["stage"],
                    "layer": meta.get("layer"),
                    "purpose": meta.get("purpose"),
                    "execution": item.get("execution", "serial"),
                    "parallel_group": item.get("parallel_group"),
                    "depends_on": item.get("depends_on", []),
                    "agent_role": item.get("agent_role"),
                    "candidate_skills": candidates,
                    "router_handled": not bool(item.get("candidate_skills")),
                }
            )
        steps.append({"step": step, "parallel": parallel, "stages": stage_entries})

    return {
        "router": registry.get("router"),
        "prompt": prompt,
        "matched": True,
        "recommended_pipeline": best["id"],
        "label": best.get("label", ""),
        "domain": best.get("domain"),
        "mode": best.get("mode", "default"),
        "score": best_score,
        "steps": steps,
        "alternatives": [{"pipeline": item["id"], "score": score} for score, item in alternatives],
        "process_report_template": "stage -> selected skill or fallback -> execution -> evidence/gate -> status",
    }


def print_stage_plan(registry: dict[str, Any], profile_items: dict[str, dict[str, Any]], pipeline: dict[str, Any]) -> None:
    stages = stage_map(registry)
    print("stage_plan:")
    for step, entries in grouped_stages(pipeline):
        parallel = len(entries) > 1 or any(item.get("execution") == "parallel" for item in entries)
        group_names = sorted({item.get("parallel_group", "") for item in entries if item.get("parallel_group")})
        step_label = f"step {step}"
        if parallel:
            suffix = f": parallel group {', '.join(group_names)}" if group_names else ": parallel"
            print(f"{step_label}{suffix}")
        else:
            print(f"{step_label}: serial")
        for item in entries:
            meta = stages.get(item["stage"], {})
            print(f"- {item['stage']}")
            if meta.get("layer"):
                print(f"  layer: {meta['layer']}")
            if meta.get("purpose"):
                print(f"  purpose: {meta['purpose']}")
            print(f"  execution: {item.get('execution', 'serial')}")
            if item.get("depends_on"):
                print(f"  depends_on: {', '.join(item['depends_on'])}")
            if item.get("agent_role"):
                print(f"  agent_role: {item['agent_role']}")
            candidates = item.get("candidate_skills", [])
            if not candidates:
                print("  route: router handles this stage directly")
                continue
            print("  candidate_skills:")
            for skill_name in candidates:
                local = profile_items.get(skill_name, {})
                status = "installed" if local.get("installed") else "recommendation"
                print(f"  - {skill_name}: {status}")
                if local.get("installed_path"):
                    print(f"    path: {local['installed_path']}")
    print("process_report_template:")
    print("- stage -> selected skill or fallback -> execution -> evidence/gate -> status")


def plan(registry: dict[str, Any], profile: dict[str, Any], prompt: str) -> None:
    selected = select_pipeline(registry, prompt)
    if selected is None:
        print("No confident pipeline match. Use the router clarification gate before selecting skills.")
        return
    best_score, best, alternatives = selected
    profile_items = installed_map(profile)

    print(f"recommended_pipeline: {best['id']}")
    print(f"label: {best.get('label', '')}")
    if best.get("domain"):
        print(f"domain: {best['domain']}")
    print(f"score: {best_score}")
    print_stage_plan(registry, profile_items, best)
    if alternatives:
        print("alternatives:")
        for score, pipeline in alternatives:
            print(f"- {pipeline['id']} ({score})")


def plan_json(registry: dict[str, Any], profile: dict[str, Any], prompt: str) -> None:
    print(json.dumps(build_plan_data(registry, profile, prompt), ensure_ascii=False, indent=2))


def show_profile(profile: dict[str, Any]) -> None:
    if not profile.get("recommended_skills"):
        print("No generated local profile found. Run scripts/install.py to scan installed skills.")
        return
    installed = [item for item in profile["recommended_skills"] if item.get("installed")]
    missing = [item for item in profile["recommended_skills"] if not item.get("installed")]
    print(f"router: {profile.get('router')}")
    print(f"installed_recommendations: {len(installed)}")
    print(f"missing_recommendations: {len(missing)}")
    for item in missing[:20]:
        print(f"- recommend: {item['name']} ({item.get('priority', 'normal')})")


def validate(registry: dict[str, Any]) -> None:
    skill_list = [skill["name"] for skill in registry.get("skills", [])]
    stage_list = [stage["id"] for stage in registry.get("stages", [])]
    layer_list = [layer["id"] for layer in registry.get("layers", [])]
    skill_names = set(skill_list)
    stage_ids = set(stage_list)
    layer_ids = set(layer_list)
    errors: list[str] = []
    if not registry.get("router"):
        errors.append("missing router field")
    if len(skill_list) != len(skill_names):
        errors.append("duplicate skill names")
    if len(stage_list) != len(stage_ids):
        errors.append("duplicate stage ids")
    if len(layer_list) != len(layer_ids):
        errors.append("duplicate layer ids")
    for stage in registry.get("stages", []):
        if layer_ids and stage.get("layer") not in layer_ids:
            errors.append(f"stage {stage['id']}: unknown layer {stage.get('layer')}")
    for skill in registry.get("skills", []):
        if layer_ids and skill.get("layer") and skill.get("layer") not in layer_ids:
            errors.append(f"skill {skill['name']}: unknown layer {skill.get('layer')}")
        for stage in skill.get("stages", []):
            if stage not in stage_ids:
                errors.append(f"skill {skill['name']}: unknown stage {stage}")
    for pipeline in registry.get("pipelines", []):
        pipeline_stages = [item.get("stage") for item in pipeline.get("stages", [])]
        for item in pipeline.get("stages", []):
            stage = item.get("stage")
            if stage not in stage_ids:
                errors.append(f"{pipeline['id']}: unknown stage {stage}")
            step = item.get("step", 0)
            if not isinstance(step, int) or step < 1:
                errors.append(f"{pipeline['id']}:{stage}: step must be a positive integer")
            execution = item.get("execution", "serial")
            if execution not in {"serial", "parallel"}:
                errors.append(f"{pipeline['id']}:{stage}: invalid execution {execution}")
            if execution == "parallel" and not item.get("parallel_group"):
                errors.append(f"{pipeline['id']}:{stage}: parallel stage missing parallel_group")
            for dependency in item.get("depends_on", []):
                if dependency not in stage_ids:
                    errors.append(f"{pipeline['id']}:{stage}: unknown dependency {dependency}")
                elif dependency not in pipeline_stages:
                    errors.append(f"{pipeline['id']}:{stage}: dependency {dependency} is not in this pipeline")
            for skill in item.get("candidate_skills", []):
                if skill not in skill_names:
                    errors.append(f"{pipeline['id']}:{stage}: unknown skill {skill}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Registry OK: {len(skill_names)} skills, {len(stage_ids)} stages, {len(registry.get('pipelines', []))} pipelines.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List skills, pipelines, or stages.")
    list_parser.add_argument("kind", choices=["skills", "pipelines", "stages", "layers"])
    search_parser = subparsers.add_parser("search", help="Search registry text.")
    search_parser.add_argument("query")
    explain_parser = subparsers.add_parser("explain", help="Explain one pipeline.")
    explain_parser.add_argument("pipeline_id")
    plan_parser = subparsers.add_parser("plan", help="Suggest a pipeline for a prompt.")
    plan_parser.add_argument("prompt")
    plan_json_parser = subparsers.add_parser("plan-json", help="Suggest a pipeline and print machine-readable JSON.")
    plan_json_parser.add_argument("prompt")
    subparsers.add_parser("profile", help="Show generated local profile summary.")
    subparsers.add_parser("validate", help="Validate registry references.")
    args = parser.parse_args()

    registry = load_registry()
    profile = load_profile()
    if args.command == "list":
        list_items(registry, profile, args.kind)
    elif args.command == "search":
        search(registry, args.query)
    elif args.command == "explain":
        explain(registry, profile, args.pipeline_id)
    elif args.command == "plan":
        plan(registry, profile, args.prompt)
    elif args.command == "plan-json":
        plan_json(registry, profile, args.prompt)
    elif args.command == "profile":
        show_profile(profile)
    elif args.command == "validate":
        validate(registry)


if __name__ == "__main__":
    main()
