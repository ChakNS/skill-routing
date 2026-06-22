#!/usr/bin/env python3
"""Inspect, validate, and plan across pluggable router modules."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULES_PATH = ROOT / "references" / "router-modules.json"


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def load_modules() -> dict[str, Any]:
    return json.loads(MODULES_PATH.read_text(encoding="utf-8"))


def as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(as_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{key} {as_text(item)}" for key, item in value.items())
    return str(value)


def list_modules(data: dict[str, Any]) -> None:
    for module in data.get("modules", []):
        status = "enabled" if module.get("enabled", True) else "disabled"
        print(f"- {module['id']}: {module.get('label', module['id'])} [{status}]")
        print(f"  skill: {resolve_path(module.get('skill_path', ''))}")
        print(f"  registry: {resolve_path(module.get('registry_path', ''))}")
        print(f"  domains: {', '.join(module.get('domains', []))}")


def validate_pipeline_registry(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"Missing registry: {path}"]
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON in {path}: {exc}"]

    skill_list = [skill.get("name") for skill in registry.get("skills", [])]
    stage_list = [stage.get("id") for stage in registry.get("stages", [])]
    layer_list = [layer.get("id") for layer in registry.get("layers", [])]
    skill_names = set(skill_list)
    stage_ids = set(stage_list)
    layer_ids = set(layer_list)
    if not registry.get("router"):
        errors.append(f"{path}: missing router field")
    if len(skill_list) != len(skill_names):
        errors.append(f"{path}: duplicate skill names")
    if len(stage_list) != len(stage_ids):
        errors.append(f"{path}: duplicate stage ids")
    if len(layer_list) != len(layer_ids):
        errors.append(f"{path}: duplicate layer ids")
    for stage in registry.get("stages", []):
        if layer_ids and stage.get("layer") not in layer_ids:
            errors.append(f"{path}: stage {stage.get('id')}: unknown layer {stage.get('layer')}")
    for skill in registry.get("skills", []):
        if layer_ids and skill.get("layer") and skill.get("layer") not in layer_ids:
            errors.append(f"{path}: skill {skill.get('name')}: unknown layer {skill.get('layer')}")
        for stage in skill.get("stages", []):
            if stage not in stage_ids:
                errors.append(f"{path}: skill {skill.get('name')}: unknown stage {stage}")
    for pipeline in registry.get("pipelines", []):
        pipeline_id = pipeline.get("id", "<unknown>")
        pipeline_stages = [item.get("stage") for item in pipeline.get("stages", [])]
        for item in pipeline.get("stages", []):
            stage = item.get("stage")
            if stage not in stage_ids:
                errors.append(f"{path}:{pipeline_id}: unknown stage {stage}")
            step = item.get("step", 0)
            if not isinstance(step, int) or step < 1:
                errors.append(f"{path}:{pipeline_id}:{stage}: step must be a positive integer")
            execution = item.get("execution", "serial")
            if execution not in {"serial", "parallel"}:
                errors.append(f"{path}:{pipeline_id}:{stage}: invalid execution {execution}")
            if execution == "parallel" and not item.get("parallel_group"):
                errors.append(f"{path}:{pipeline_id}:{stage}: parallel stage missing parallel_group")
            for dependency in item.get("depends_on", []):
                if dependency not in stage_ids:
                    errors.append(f"{path}:{pipeline_id}:{stage}: unknown dependency {dependency}")
                elif dependency not in pipeline_stages:
                    errors.append(f"{path}:{pipeline_id}:{stage}: dependency {dependency} is not in this pipeline")
            for skill in item.get("candidate_skills", []):
                if skill not in skill_names:
                    errors.append(f"{path}:{pipeline_id}:{stage}: unknown skill {skill}")
    return errors


def validate_modules(data: dict[str, Any]) -> None:
    errors: list[str] = []
    seen: set[str] = set()
    for module in data.get("modules", []):
        module_id = module.get("id")
        if not module_id:
            errors.append("Module missing id")
            continue
        if module_id in seen:
            errors.append(f"Duplicate module id: {module_id}")
        seen.add(module_id)

        skill_path = resolve_path(module.get("skill_path", ""))
        registry_path = resolve_path(module.get("registry_path", ""))
        if not (skill_path / "SKILL.md").exists():
            errors.append(f"{module_id}: missing SKILL.md at {skill_path}")
        errors.extend(validate_pipeline_registry(registry_path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Router modules OK: {len(data.get('modules', []))} modules.")


def classify_module(data: dict[str, Any], prompt: str) -> dict[str, Any] | None:
    text = prompt.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for module in data.get("modules", []):
        if not module.get("enabled", True):
            continue
        score = 0
        blob = as_text(module).lower()
        for token in set(text.replace("/", " ").replace("-", " ").split()):
            if len(token) >= 4 and token in blob:
                score += 1
        if module["id"] == "content":
            for token in ["post", "write", "content", "newsletter", "xiaohongshu", "linkedin", "thumbnail", "publish", "小红书", "图文", "笔记", "内容", "写作", "封面", "发布"]:
                if token in text:
                    score += 3
        if module["id"] == "coding":
            for token in ["code", "bug", "test", "react", "api", "deploy", "github", "frontend", "backend", "debug", "代码", "修复", "测试", "前端", "后端", "部署", "路由", "skill", "插件"]:
                if token in text:
                    score += 3
        if score:
            scored.append((score, module))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def plan(data: dict[str, Any], prompt: str) -> None:
    module = classify_module(data, prompt)
    if module is None:
        print("No confident module match. Ask a clarification question or inspect module domains.")
        return

    print(f"recommended_module: {module['id']}")
    print(f"label: {module.get('label', '')}")
    print(f"skill_path: {resolve_path(module.get('skill_path', ''))}")
    print(f"registry_path: {resolve_path(module.get('registry_path', ''))}")

    router_cli = resolve_path(module.get("skill_path", "")) / "scripts" / "router_registry.py"
    if router_cli.exists():
        result = subprocess.run([sys.executable, str(router_cli), "plan", prompt], text=True, capture_output=True)
        if result.stdout:
            print("domain_plan:")
            print(result.stdout.rstrip())
        if result.returncode != 0:
            print(result.stderr.rstrip(), file=sys.stderr)
            raise SystemExit(result.returncode)


def plan_json(data: dict[str, Any], prompt: str) -> None:
    module = classify_module(data, prompt)
    if module is None:
        print(
            json.dumps(
                {
                    "prompt": prompt,
                    "matched": False,
                    "message": "No confident module match. Ask a clarification question or inspect module domains.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    result_data: dict[str, Any] = {
        "prompt": prompt,
        "matched": True,
        "recommended_module": module["id"],
        "label": module.get("label", ""),
        "skill_path": str(resolve_path(module.get("skill_path", ""))),
        "registry_path": str(resolve_path(module.get("registry_path", ""))),
    }

    router_cli = resolve_path(module.get("skill_path", "")) / "scripts" / "router_registry.py"
    if router_cli.exists():
        result = subprocess.run([sys.executable, str(router_cli), "plan-json", prompt], text=True, capture_output=True)
        if result.returncode != 0:
            print(result.stderr.rstrip(), file=sys.stderr)
            raise SystemExit(result.returncode)
        if result.stdout:
            result_data["domain_plan"] = json.loads(result.stdout)
    print(json.dumps(result_data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List registered router modules.")
    subparsers.add_parser("validate", help="Validate module paths and pipeline registries.")
    plan_parser = subparsers.add_parser("plan", help="Recommend a domain router for a prompt.")
    plan_parser.add_argument("prompt")
    plan_json_parser = subparsers.add_parser("plan-json", help="Recommend a domain router and print machine-readable JSON.")
    plan_json_parser.add_argument("prompt")
    args = parser.parse_args()

    data = load_modules()
    if args.command == "list":
        list_modules(data)
    elif args.command == "validate":
        validate_modules(data)
    elif args.command == "plan":
        plan(data, args.prompt)
    elif args.command == "plan-json":
        plan_json(data, args.prompt)


if __name__ == "__main__":
    main()
