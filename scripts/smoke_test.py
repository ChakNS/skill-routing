#!/usr/bin/env python3
"""Exercise installation, initialization, routing, and release-facing CLIs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=True,
        env=env,
        timeout=timeout,
    )
    return result.stdout.strip()


def run_expect_failure(
    cmd: list[str],
    expected: str,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    result = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
    )
    if result.returncode == 0:
        raise AssertionError(f"Expected command to fail: {' '.join(cmd)}")
    output = f"{result.stdout}\n{result.stderr}"
    if expected not in output:
        raise AssertionError(f"Expected {expected!r} in failure output:\n{output}")


def write_skill(root: Path, name: str, description: str) -> None:
    directory = root / "team" / "nested" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def load_plan(router: Path, state: Path, prompt: str) -> dict:
    return json.loads(run([sys.executable, str(router), "--state", str(state), "plan-json", prompt]))


def stage(plan: dict, stage_id: str) -> dict:
    return next(
        item
        for step in plan["domain_plan"]["steps"]
        for item in step["stages"]
        if item["stage"] == stage_id
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="routing-skills-smoke-") as tmp:
        base = Path(tmp)
        target = base / "agents-skills"
        shell_target = base / "shell-skills"
        local = base / "local-skills"
        write_skill(
            local,
            "private-tech-editor",
            "Use when editing Chinese AI technical articles for natural voice while preserving terminology.",
        )

        run(
            [
                sys.executable,
                "scripts/install.py",
                "--target",
                str(target),
                "--modules",
                "all",
                "--no-default-scan-roots",
                "--scan-root",
                str(local),
            ]
        )

        shell_env = os.environ.copy()
        shell_env.update(
            {
                "ROUTING_SKILLS_SOURCE_DIR": str(ROOT),
                "ROUTING_SKILLS_TARGET": str(shell_target),
                "ROUTING_SKILLS_MODULES": "main,content",
                "ROUTING_SKILLS_NO_DEFAULT_SCAN_ROOTS": "1",
                "ROUTING_SKILLS_SCAN_ROOT": str(local),
            }
        )
        run(["bash", "scripts/install.sh"], env=shell_env)

        router = target / "skill-routing" / "scripts" / "router_modules.py"
        content_router = target / "content-skill-routing" / "scripts" / "router_registry.py"
        coding_router = target / "coding-skill-routing" / "scripts" / "router_registry.py"
        state_path = target / ".skill-routing" / "profile.json"
        shell_router = shell_target / "skill-routing" / "scripts" / "router_modules.py"

        if not state_path.exists():
            raise AssertionError("Installer did not create the personal profile")
        profile = json.loads(state_path.read_text(encoding="utf-8"))
        if "private-tech-editor" not in {item["name"] for item in profile["catalog"]}:
            raise AssertionError("Recursive local skill discovery did not populate the profile")

        for command, expected in (
            ([sys.executable, str(router), "validate"], "Router modules OK"),
            ([sys.executable, str(shell_router), "validate"], "Router modules OK"),
            ([sys.executable, str(content_router), "validate"], "Registry OK"),
            ([sys.executable, str(coding_router), "validate"], "Registry OK"),
        ):
            if expected not in run(command):
                raise AssertionError(f"Expected {expected!r} from {' '.join(command)}")

        direct = load_plan(router, state_path, "把这篇中文 AI 技术文章改得自然一些，但保留准确术语")
        if direct["route_kind"] != "direct" or direct["selected_skills"][0]["name"] != "private-tech-editor":
            raise AssertionError(f"Unexpected direct route: {direct}")

        content = load_plan(router, state_path, "生成一套小红书图文笔记，包含标题、正文、封面方向和发布清单")
        if content.get("recommended_module") != "content":
            raise AssertionError(f"Unexpected content route: {content}")
        if content["domain_plan"]["recommended_pipeline"] != "xhs_note_package":
            raise AssertionError(f"Unexpected content pipeline: {content}")
        title_resolution = stage(content, "title_hook")["resolution"]
        if title_resolution["status"] != "decision_required":
            raise AssertionError(f"Missing skill did not require a decision: {title_resolution}")
        if {item["action"] for item in title_resolution["actions"]} != {"install", "replace", "fallback", "disable"}:
            raise AssertionError(f"Missing-skill choices are incomplete: {title_resolution}")

        coding = load_plan(router, state_path, "改进这个 skill 安装器并先补回归测试")
        if coding.get("recommended_module") != "coding":
            raise AssertionError(f"Unexpected coding route: {coding}")
        if coding["domain_plan"]["recommended_pipeline"] != "skill_development":
            raise AssertionError(f"Unexpected coding pipeline: {coding}")

        composed = load_plan(router, state_path, "Build a React content calendar web app and write the launch post")
        if composed["route_kind"] != "composed_pipeline" or set(composed["recommended_modules"]) != {"coding", "content"}:
            raise AssertionError(f"Unexpected composed route: {composed}")

        doctor = json.loads(run([sys.executable, str(router), "doctor"]))
        if not doctor["ok"] or doctor["effective_skills"] < 1:
            raise AssertionError(f"Doctor reported an unhealthy installation: {doctor}")

        eval_output = run([sys.executable, "scripts/evaluate_routes.py"])
        if "Routing evals:" not in eval_output:
            raise AssertionError(f"Routing evaluator did not report results:\n{eval_output}")

        empty_evals = base / "empty-evals.json"
        empty_evals.write_text('{"cases": []}\n', encoding="utf-8")
        run_expect_failure(
            [sys.executable, "scripts/evaluate_routes.py", "--evals", str(empty_evals)],
            "routing eval set is empty",
        )
        run_expect_failure(
            [sys.executable, "scripts/install.py", "--target", str(ROOT / "skills"), "--modules", "main"],
            "source tree",
        )

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
