#!/usr/bin/env python3
"""Run deterministic routing, abstention, fallback, and personalization evals."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALS = ROOT / "evals" / "routing-evals.json"
MAIN_ROUTER = ROOT / "skills" / "skill-routing" / "scripts" / "router_modules.py"


def write_fixture_skills(root: Path, fixtures: list[dict[str, str]]) -> None:
    for fixture in fixtures:
        directory = root / fixture["name"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            "---\n"
            f"name: {fixture['name']}\n"
            f"description: {fixture['description']}\n"
            "---\n\n"
            f"# {fixture['name']}\n",
            encoding="utf-8",
        )


def prepare_state(case: dict[str, Any], workspace: Path) -> Path | None:
    fixtures = case.get("inventory", [])
    resolutions = case.get("resolutions", [])
    if not fixtures and not resolutions and not case.get("initialize", False):
        return None
    skill_root = workspace / "skills"
    state = workspace / "profile.json"
    skill_root.mkdir(parents=True, exist_ok=True)
    write_fixture_skills(skill_root, fixtures)
    init = subprocess.run(
        [
            sys.executable,
            str(MAIN_ROUTER),
            "--state",
            str(state),
            "init",
            "--no-default-scan-roots",
            "--scan-root",
            str(skill_root),
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if init.returncode != 0:
        raise RuntimeError(f"eval init failed for {case['id']}: {init.stderr or init.stdout}")
    for resolution in resolutions:
        command = [
            sys.executable,
            str(MAIN_ROUTER),
            "--state",
            str(state),
            "resolve",
            "--module",
            resolution["module"],
            "--stage",
            resolution["stage"],
            "--skill",
            resolution["skill"],
            "--action",
            resolution["action"],
        ]
        if resolution.get("replacement"):
            command.extend(["--replacement", resolution["replacement"]])
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"eval resolution failed for {case['id']}: {result.stderr or result.stdout}")
    return state


def run_plan(prompt: str, state: Path) -> dict[str, Any]:
    # Always pass an isolated state path. Falling back to the installed router's
    # default profile would make release evals depend on the developer's skills.
    command = [sys.executable, str(MAIN_ROUTER), "--state", str(state)]
    command.extend(["plan-json", prompt])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout)


def domain_plans(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if plan.get("domain_plans"):
        return plan["domain_plans"]
    module = plan.get("recommended_module")
    if module and plan.get("domain_plan"):
        return {module: plan["domain_plan"]}
    return {}


def flatten(
    plan: dict[str, Any],
) -> tuple[set[str], set[str], dict[str, str], dict[str, set[str]]]:
    stages: set[str] = set()
    groups: set[str] = set()
    statuses: dict[str, str] = {}
    missing_candidates: dict[str, set[str]] = defaultdict(set)
    for module, domain_plan in domain_plans(plan).items():
        for step in domain_plan.get("steps", []):
            for stage in step.get("stages", []):
                stage_id = stage.get("stage", "")
                stage_key = f"{module}:{stage_id}"
                stages.add(stage_id)
                if stage.get("parallel_group"):
                    groups.add(stage["parallel_group"])
                resolution = stage.get("resolution", {})
                statuses[stage_key] = resolution.get("status", "")
                missing_candidates[stage_key].update(resolution.get("missing", []))
    return stages, groups, statuses, missing_candidates


def selected_names(plan: dict[str, Any]) -> set[str]:
    return {item["name"] for item in plan.get("selected_skills", [])}


def alternative_pipelines(plan: dict[str, Any]) -> set[str]:
    return {
        item["pipeline"]
        for item in plan.get("alternatives", [])
        if isinstance(item, dict) and item.get("pipeline")
    }


def alternative_names(plan: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in plan.get("alternatives", [])
        if isinstance(item, dict) and item.get("name")
    }


def evaluate_case(case: dict[str, Any], workspace: Path) -> dict[str, Any]:
    state = prepare_state(case, workspace) or (workspace / "uninitialized-profile.json")
    plan = run_plan(case["prompt"], state)
    stages, parallel_groups, statuses, stage_missing = flatten(plan)
    failures: list[str] = []

    expected_kinds = set(case.get("expected_route_kinds", [case.get("expected_route_kind")])) - {None}
    if expected_kinds and plan.get("route_kind") not in expected_kinds:
        failures.append(f"route kind expected one of {sorted(expected_kinds)}, got {plan.get('route_kind')}")

    if "expected_matched" in case and bool(plan.get("matched")) != bool(case["expected_matched"]):
        failures.append(f"matched expected {case['expected_matched']}, got {plan.get('matched')}")

    actual_modules = set(plan.get("recommended_modules", []))
    if not actual_modules and plan.get("recommended_module"):
        actual_modules.add(plan["recommended_module"])
    expected_modules = set(case.get("expected_modules", []))
    if expected_modules and actual_modules != expected_modules:
        failures.append(f"modules expected {sorted(expected_modules)}, got {sorted(actual_modules)}")
    forbidden_modules = set(case.get("forbidden_modules", [])) & actual_modules
    if forbidden_modules:
        failures.append(f"forbidden modules selected: {sorted(forbidden_modules)}")

    plans = domain_plans(plan)
    expected_pipelines = case.get("expected_pipelines", {})
    for module, acceptable in expected_pipelines.items():
        actual = plans.get(module, {}).get("recommended_pipeline")
        if actual not in acceptable:
            failures.append(f"{module} pipeline expected one of {acceptable}, got {actual}")
    actual_pipelines = {item.get("recommended_pipeline") for item in plans.values()}
    forbidden_pipelines = set(case.get("forbidden_pipelines", [])) & actual_pipelines
    if forbidden_pipelines:
        failures.append(f"forbidden pipelines selected: {sorted(forbidden_pipelines)}")

    actual_alternative_pipelines = alternative_pipelines(plan)
    missing_alternative_pipelines = sorted(
        set(case.get("required_alternative_pipelines", [])) - actual_alternative_pipelines
    )
    if missing_alternative_pipelines:
        failures.append(f"missing alternative pipelines: {missing_alternative_pipelines}")
    forbidden_alternative_pipelines = sorted(
        set(case.get("forbidden_alternative_pipelines", [])) & actual_alternative_pipelines
    )
    if forbidden_alternative_pipelines:
        failures.append(f"forbidden alternative pipelines: {forbidden_alternative_pipelines}")

    missing_stages = sorted(set(case.get("required_stages", [])) - stages)
    if missing_stages:
        failures.append(f"missing stages: {missing_stages}")
    forbidden_stages = sorted(set(case.get("forbidden_stages", [])) & stages)
    if forbidden_stages:
        failures.append(f"forbidden stages: {forbidden_stages}")
    missing_groups = sorted(set(case.get("required_parallel_groups", [])) - parallel_groups)
    if missing_groups:
        failures.append(f"missing parallel groups: {missing_groups}")

    missing_skills = sorted(set(case.get("required_selected_skills", [])) - selected_names(plan))
    if missing_skills:
        failures.append(f"missing selected skills: {missing_skills}")
    forbidden_skills = sorted(set(case.get("forbidden_selected_skills", [])) & selected_names(plan))
    if forbidden_skills:
        failures.append(f"forbidden selected skills: {forbidden_skills}")

    actual_alternative_skills = alternative_names(plan)
    missing_alternative_skills = sorted(
        set(case.get("required_alternative_skills", [])) - actual_alternative_skills
    )
    if missing_alternative_skills:
        failures.append(f"missing alternative skills: {missing_alternative_skills}")
    forbidden_alternative_skills = sorted(
        set(case.get("forbidden_alternative_skills", [])) & actual_alternative_skills
    )
    if forbidden_alternative_skills:
        failures.append(f"forbidden alternative skills: {forbidden_alternative_skills}")

    for key, expected in case.get("expected_stage_status", {}).items():
        if statuses.get(key) != expected:
            failures.append(f"stage status {key} expected {expected}, got {statuses.get(key)}")

    for key, required in case.get("required_stage_missing", {}).items():
        absent = sorted(set(required) - stage_missing.get(key, set()))
        if absent:
            failures.append(f"stage missing candidates {key} did not include: {absent}")
    for key, forbidden in case.get("forbidden_stage_missing", {}).items():
        leaked = sorted(set(forbidden) & stage_missing.get(key, set()))
        if leaked:
            failures.append(f"stage missing candidates {key} included forbidden: {leaked}")

    minimum = case.get("min_confidence")
    if minimum is not None and float(plan.get("confidence", 0)) < float(minimum):
        failures.append(f"confidence expected >= {minimum}, got {plan.get('confidence')}")

    return {
        "id": case["id"],
        "slices": case.get("slices", []),
        "passed": not failures,
        "failures": failures,
        "route_kind": plan.get("route_kind"),
        "modules": sorted(actual_modules),
        "pipelines": sorted(item for item in actual_pipelines if item),
        "selected_skills": sorted(selected_names(plan)),
        "alternative_pipelines": sorted(actual_alternative_pipelines),
        "alternative_skills": sorted(actual_alternative_skills),
        "confidence": plan.get("confidence"),
    }


def aggregate_slices(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals: Counter[str] = Counter()
    passed: Counter[str] = Counter()
    for result in results:
        for slice_name in result.get("slices", []):
            totals[slice_name] += 1
            if result["passed"]:
                passed[slice_name] += 1
    return {
        name: {"passed": passed[name], "total": totals[name]}
        for name in sorted(totals)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evals", default=str(DEFAULT_EVALS), help="Path to routing eval JSON.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    data = json.loads(Path(args.evals).read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if not cases:
        print("ERROR: routing eval set is empty", file=sys.stderr)
        raise SystemExit(2)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="routing-evals-") as tmp:
        root = Path(tmp)
        for index, case in enumerate(cases):
            results.append(evaluate_case(case, root / f"{index:03d}-{case['id']}"))

    count_passed = sum(1 for result in results if result["passed"])
    total = len(results)
    output = {
        "passed": count_passed,
        "total": total,
        "pass_rate": round(count_passed / total, 4),
        "slices": aggregate_slices(results),
        "results": results,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status} {result['id']}: {result['route_kind']} {result['modules']} {result['pipelines']}")
            for failure in result["failures"]:
                print(f"  - {failure}")
        print(f"Routing evals: {count_passed}/{total} passed ({output['pass_rate']:.1%}).")
    if count_passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
