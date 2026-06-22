#!/usr/bin/env python3
"""Run routing regression evals against the workflow routing matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALS = ROOT / "evals" / "routing-evals.json"
MAIN_ROUTER = ROOT / "skills" / "skill-routing" / "scripts" / "router_modules.py"


def run_plan(prompt: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(MAIN_ROUTER), "plan-json", prompt],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def flatten_stages(plan: dict[str, Any]) -> tuple[set[str], set[str]]:
    domain_plan = plan.get("domain_plan", {})
    stages: set[str] = set()
    parallel_groups: set[str] = set()
    for step in domain_plan.get("steps", []):
        for stage in step.get("stages", []):
            stages.add(stage.get("stage", ""))
            group = stage.get("parallel_group")
            if group:
                parallel_groups.add(group)
    return stages, parallel_groups


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    plan = run_plan(case["prompt"])
    stages, parallel_groups = flatten_stages(plan)
    domain_plan = plan.get("domain_plan", {})
    failures: list[str] = []

    if plan.get("recommended_module") != case["expected_module"]:
        failures.append(f"module expected {case['expected_module']}, got {plan.get('recommended_module')}")
    if domain_plan.get("recommended_pipeline") != case["expected_pipeline"]:
        failures.append(f"pipeline expected {case['expected_pipeline']}, got {domain_plan.get('recommended_pipeline')}")

    missing_stages = sorted(set(case.get("required_stages", [])) - stages)
    if missing_stages:
        failures.append(f"missing stages: {', '.join(missing_stages)}")

    missing_groups = sorted(set(case.get("required_parallel_groups", [])) - parallel_groups)
    if missing_groups:
        failures.append(f"missing parallel groups: {', '.join(missing_groups)}")

    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "recommended_module": plan.get("recommended_module"),
        "recommended_pipeline": domain_plan.get("recommended_pipeline"),
        "stages": sorted(stages),
        "parallel_groups": sorted(parallel_groups),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evals", default=str(DEFAULT_EVALS), help="Path to routing eval JSON.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    data = json.loads(Path(args.evals).read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in data.get("cases", [])]
    passed = sum(1 for result in results if result["passed"])
    total = len(results)

    if args.json:
        print(json.dumps({"passed": passed, "total": total, "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status} {result['id']}: {result['recommended_module']} -> {result['recommended_pipeline']}")
            for failure in result["failures"]:
                print(f"  - {failure}")
        print(f"Routing evals: {passed}/{total} passed.")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
