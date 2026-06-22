#!/usr/bin/env python3
"""Smoke test installation and router CLI behavior without external dependencies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd or ROOT, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def run_expect_failure(cmd: list[str], expected: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(cmd, cwd=cwd or ROOT, text=True, capture_output=True, env=env)
    if result.returncode == 0:
        raise AssertionError(f"Expected command to fail: {' '.join(cmd)}")
    output = f"{result.stdout}\n{result.stderr}"
    if expected not in output:
        raise AssertionError(f"Expected {expected!r} in failure output:\n{output}")


def assert_contains(text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"Expected {needle!r} in output:\n{text}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="routing-skills-") as tmp:
        target = Path(tmp) / "skills"
        one_line_target = Path(tmp) / "one-line-skills"
        run([
            sys.executable,
            "scripts/install.py",
            "--target",
            str(target),
            "--modules",
            "all",
            "--no-default-scan-roots",
            "--scan-root",
            str(target),
        ])
        env = os.environ.copy()
        env.update({
            "ROUTING_SKILLS_SOURCE_DIR": str(ROOT),
            "ROUTING_SKILLS_TARGET": str(one_line_target),
            "ROUTING_SKILLS_MODULES": "main,content",
            "ROUTING_SKILLS_NO_DEFAULT_SCAN_ROOTS": "1",
            "ROUTING_SKILLS_SCAN_ROOT": str(one_line_target),
        })
        subprocess.run(["bash", "-c", "cat scripts/install.sh | bash"], cwd=ROOT, text=True, capture_output=True, check=True, env=env)

        main_router = target / "skill-routing" / "scripts" / "router_modules.py"
        content_router = target / "content-skill-routing" / "scripts" / "router_registry.py"
        coding_router = target / "coding-skill-routing" / "scripts" / "router_registry.py"
        one_line_main_router = one_line_target / "skill-routing" / "scripts" / "router_modules.py"

        assert_contains(run([sys.executable, "skills/skill-routing/scripts/router_modules.py", "validate"]), "Router modules OK")
        assert_contains(run([sys.executable, str(main_router), "validate"]), "Router modules OK")
        assert_contains(run([sys.executable, str(content_router), "validate"]), "Registry OK")
        assert_contains(run([sys.executable, str(coding_router), "validate"]), "Registry OK")
        assert_contains(run([sys.executable, str(one_line_main_router), "validate"]), "Router modules OK")

        content_plan = run([sys.executable, str(content_router), "plan", "write a xiaohongshu post and prepare cover card handoff"])
        content_plan_zh = run([sys.executable, str(content_router), "plan", "生成一套小红书图文笔记，包含标题、正文、封面方向和发布清单"])
        content_plan_json = run([sys.executable, str(content_router), "plan-json", "生成一套小红书图文笔记，包含标题、正文、封面方向和发布清单"])
        coding_plan = run([sys.executable, str(coding_router), "plan", "fix a failing React component test and verify in browser"])
        coding_plan_json = run([sys.executable, str(coding_router), "plan-json", "改进这个skill安装器并补测试"])
        main_plan = run([sys.executable, str(main_router), "plan", "debug this API and add tests"])
        main_plan_zh = run([sys.executable, "skills/skill-routing/scripts/router_modules.py", "plan", "帮我生成一套小红书图文笔记"])
        main_plan_json = run([sys.executable, "skills/skill-routing/scripts/router_modules.py", "plan-json", "帮我生成一套小红书图文笔记"])

        assert_contains(content_plan, "recommended_pipeline")
        assert_contains(content_plan_zh, "recommended_pipeline")
        assert_contains(content_plan_zh, "xhs_note_package")
        if json.loads(content_plan_json)["recommended_pipeline"] != "xhs_note_package":
            raise AssertionError("content plan-json did not return xhs_note_package")
        assert_contains(content_plan, "parallel group")
        assert_contains(content_plan, "process_report_template")
        assert_contains(content_plan, "recommendation")
        assert_contains(coding_plan, "recommended_pipeline")
        if json.loads(coding_plan_json)["recommended_pipeline"] != "skill_development":
            raise AssertionError("coding plan-json did not return skill_development")
        assert_contains(coding_plan, "parallel group")
        assert_contains(coding_plan, "process_report_template")
        assert_contains(coding_plan, "recommendation")
        assert_contains(main_plan, "recommended_module")
        assert_contains(main_plan_zh, "recommended_module: content")
        assert_contains(main_plan_zh, "xhs_note_package")
        if json.loads(main_plan_json)["domain_plan"]["recommended_pipeline"] != "xhs_note_package":
            raise AssertionError("main plan-json did not return xhs_note_package")

        profile_path = target / "content-skill-routing" / "references" / "local-skill-profile.generated.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if "recommended_skills" not in profile:
            raise AssertionError("Generated profile missing recommended_skills")
        first_skill = profile["recommended_skills"][0]
        if "category" not in first_skill or "parallel_safe" not in first_skill:
            raise AssertionError("Generated profile missing routing metadata")

        assert_contains(run([sys.executable, "scripts/evaluate_routes.py"]), "Routing evals:")

        run_expect_failure(
            [sys.executable, "scripts/install.py", "--target", "skills", "--modules", "main"],
            "Refusing to install into the source skills directory",
        )
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
