from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills" / "skill-routing" / "scripts" / "router_modules.py"
INSTALLER = ROOT / "scripts" / "install.py"


def write_skill(root: Path, name: str, description: str, *, nested: str = "") -> Path:
    directory = root / nested / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return path


class PersonalRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="skill-routing-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.skill_root = self.base / "skills"
        self.state = self.base / "profile.json"

    def cli(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROUTER), "--state", str(self.state), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=check,
        )

    def initialize(self) -> dict:
        result = self.cli(
            "init",
            "--no-default-scan-roots",
            "--scan-root",
            str(self.skill_root),
            "--json",
        )
        return json.loads(result.stdout)

    def route(self, prompt: str) -> dict:
        return json.loads(self.cli("plan-json", prompt).stdout)

    def test_init_recursively_indexes_arbitrary_skills_without_executing_them(self) -> None:
        marker = self.base / "must-not-exist"
        skill = write_skill(
            self.skill_root,
            "humanizer-tech-zh",
            "Use when Chinese technical writing needs a natural human voice while preserving terminology.",
            nested="team/nested",
        )
        (skill.parent / "payload.sh").write_text(f"touch {marker}\n", encoding="utf-8")

        summary = self.initialize()
        profile = json.loads(self.state.read_text(encoding="utf-8"))

        self.assertEqual(summary["inventory"]["effective_skills"], 1)
        self.assertEqual(profile["catalog"][0]["name"], "humanizer-tech-zh")
        self.assertIn("natural human voice", profile["catalog"][0]["description"])
        self.assertFalse(marker.exists(), "discovery must never execute discovered skill resources")

    def test_init_reports_duplicate_names_instead_of_silently_dropping_them(self) -> None:
        first = write_skill(self.skill_root / "first", "same-name", "Use when editing release notes for clarity.")
        second = write_skill(self.skill_root / "second", "same-name", "Use when editing release notes for clarity.")

        summary = self.initialize()

        self.assertEqual(summary["inventory"]["effective_skills"], 1)
        self.assertEqual(summary["inventory"]["conflicts"], 1)
        profile = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(len(profile["conflicts"][0]["paths"]), 2)
        self.assertTrue(profile["catalog"][0]["conflict_unresolved"])

        unresolved = self.route("Edit these release notes for clarity")
        self.assertNotIn("same-name", [item["name"] for item in unresolved["selected_skills"]])

        self.cli("resolve-conflict", "--skill", "same-name", "--path", str(second.parent))
        resolved = self.route("Edit these release notes for clarity")
        self.assertEqual(resolved["selected_skills"][0]["name"], "same-name")
        self.assertEqual(Path(resolved["selected_skills"][0]["path"]), second.parent.resolve())
        self.assertNotEqual(first.parent.resolve(), second.parent.resolve())

        second.unlink()
        self.cli("refresh", "--json")
        stale = self.route("Edit these release notes for clarity")
        self.assertNotIn("same-name", [item["name"] for item in stale["selected_skills"]])
        stale_profile = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertTrue(stale_profile["catalog"][0]["conflict_unresolved"])

    def test_init_refuses_to_downgrade_future_profile_schema(self) -> None:
        future = {
            "schema_version": 999,
            "future_important": {"token": "keep-me"},
            "catalog": [],
            "conflicts": [],
            "bindings": {},
            "resolutions": {},
            "preferences": {"disabled_skills": [], "preferred_paths": {}},
            "feedback": {},
            "history": [],
        }
        self.state.write_text(json.dumps(future), encoding="utf-8")

        result = self.cli("init", "--no-default-scan-roots", "--json", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported schema", result.stderr + result.stdout)
        preserved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(preserved["schema_version"], 999)
        self.assertEqual(preserved["future_important"], {"token": "keep-me"})

    def test_discovery_rejects_skill_file_symlinks_that_escape_the_scan_root(self) -> None:
        outside = write_skill(self.base / "outside", "outside-skill", "Use for private external work.")
        link_dir = self.skill_root / "linked"
        link_dir.mkdir(parents=True, exist_ok=True)
        try:
            (link_dir / "SKILL.md").symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        summary = self.initialize()
        profile = json.loads(self.state.read_text(encoding="utf-8"))

        self.assertEqual(summary["inventory"]["effective_skills"], 0)
        self.assertTrue(any("outside scan root" in warning for warning in profile["scan_warnings"]))

    def test_discovery_skips_oversized_skill_files_instead_of_fingerprinting_them(self) -> None:
        directory = self.skill_root / "oversized"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            "---\nname: oversized\ndescription: Use for oversized test data.\n---\n" + ("x" * 300_000),
            encoding="utf-8",
        )

        summary = self.initialize()
        profile = json.loads(self.state.read_text(encoding="utf-8"))

        self.assertEqual(summary["inventory"]["effective_skills"], 0)
        self.assertTrue(any("exceeds" in warning for warning in profile["scan_warnings"]))

    def test_direct_route_uses_a_local_skill_outside_bundled_route_packs(self) -> None:
        write_skill(
            self.skill_root,
            "humanizer-tech-zh",
            "Use when Chinese technical or AI writing should sound natural and less machine-generated while preserving precise terminology.",
        )
        self.initialize()

        plan = self.route("请把这篇中文 AI 技术文章改得更自然，去掉机器味但保留术语准确性")

        self.assertTrue(plan["matched"])
        self.assertEqual(plan["route_kind"], "direct")
        self.assertEqual(plan["selected_skills"][0]["name"], "humanizer-tech-zh")
        self.assertGreater(plan["confidence"], 0)

    def test_missing_dependency_returns_explicit_user_decision_actions(self) -> None:
        self.initialize()

        plan = self.route("生成一套小红书图文笔记，包含标题、正文、封面方向和发布清单")
        title_stage = next(
            stage
            for step in plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "title_hook"
        )

        self.assertEqual(title_stage["resolution"]["status"], "decision_required")
        self.assertEqual(
            {item["action"] for item in title_stage["resolution"]["actions"]},
            {"install", "replace", "fallback", "disable"},
        )
        self.assertTrue(all(item.get("requires_confirmation", False) for item in title_stage["resolution"]["actions"] if item["action"] == "install"))

    def test_replacement_resolution_is_persisted_and_used(self) -> None:
        write_skill(self.skill_root, "my-title-tool", "Use for a private editorial workflow.")
        self.initialize()
        self.cli(
            "resolve",
            "--module",
            "content",
            "--stage",
            "title_hook",
            "--skill",
            "hook-generator",
            "--action",
            "replace",
            "--replacement",
            "my-title-tool",
        )

        plan = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        title_stage = next(
            stage
            for step in plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "title_hook"
        )

        self.assertEqual(title_stage["resolution"]["status"], "selected")
        self.assertEqual(title_stage["resolution"]["selected"][0]["name"], "my-title-tool")
        self.assertEqual(title_stage["resolution"]["selected"][0]["reason"], "user replacement")

    def test_manual_binding_overrides_an_installed_route_pack_candidate(self) -> None:
        write_skill(self.skill_root, "hook-generator", "Use when generating social post hooks and titles.")
        write_skill(self.skill_root, "my-title-tool", "Use when generating social post hooks and titles.")
        self.initialize()
        self.cli("bind", "--module", "content", "--stage", "title_hook", "--skill", "my-title-tool")

        plan = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        title_stage = next(
            stage
            for step in plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "title_hook"
        )

        self.assertEqual(title_stage["resolution"]["selected"][0]["name"], "my-title-tool")
        self.assertEqual(title_stage["resolution"]["selected"][0]["reason"], "manual binding")

    def test_fallback_and_disabled_node_choices_change_future_routes(self) -> None:
        self.initialize()
        self.cli(
            "resolve",
            "--module",
            "content",
            "--stage",
            "title_hook",
            "--skill",
            "hook-generator",
            "--action",
            "fallback",
        )
        fallback_plan = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        fallback_stage = next(
            stage
            for step in fallback_plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "title_hook"
        )
        self.assertEqual(fallback_stage["resolution"]["status"], "agent_fallback")

        self.cli(
            "resolve",
            "--module",
            "content",
            "--stage",
            "visual_direction",
            "--skill",
            "xhs-visual-director",
            "--action",
            "disable",
        )
        disabled_plan = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        disabled_stage = next(
            stage
            for step in disabled_plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "visual_direction"
        )
        self.assertEqual(disabled_stage["resolution"]["status"], "disabled")

    def test_disabling_one_alternative_does_not_disable_the_whole_stage(self) -> None:
        self.initialize()
        self.cli(
            "resolve",
            "--module",
            "content",
            "--stage",
            "asset_generation",
            "--skill",
            "guizang-social-card-skill",
            "--action",
            "disable",
        )

        plan = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        asset_stage = next(
            stage
            for step in plan["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "asset_generation"
        )

        self.assertEqual(asset_stage["resolution"]["status"], "decision_required")
        self.assertEqual(asset_stage["resolution"]["missing"], ["imagegen"])
        self.assertEqual(asset_stage["resolution"]["actions"][0]["skill"], "imagegen")

    def test_resolve_rejects_unknown_route_targets(self) -> None:
        self.initialize()

        result = self.cli(
            "resolve",
            "--module",
            "typo",
            "--stage",
            "no-such-stage",
            "--skill",
            "no-such-skill",
            "--action",
            "fallback",
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown module", result.stderr)

    def test_validate_rejects_malformed_v3_route_pack_contract(self) -> None:
        registry_path = self.base / "invalid-registry.json"
        modules_path = self.base / "modules.json"
        registry_path.write_text(
            json.dumps(
                {
                    "router": "invalid-router",
                    "version": 3,
                    "layers": [{"id": "known", "label": "Known", "purpose": "test"}, "bad-layer"],
                    "stages": [{"id": "stage", "layer": "missing", "purpose": "test"}],
                    "skills": [],
                    "pipelines": [
                        {
                            "id": "broken",
                            "label": "Broken",
                            "domain": "test",
                            "mode": "nonsense",
                            "triggers": [1],
                            "stages": ["bad-stage"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        modules_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "modules": [
                        {
                            "id": "invalid",
                            "skill_path": str(self.base),
                            "registry_path": str(registry_path),
                            "enabled": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(ROUTER),
                "--state",
                str(self.state),
                "--modules-file",
                str(modules_path),
                "validate",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("layers must contain only objects", result.stderr)
        self.assertIn("triggers must contain only non-empty strings", result.stderr)
        self.assertIn("stages must contain only objects", result.stderr)
        self.assertIn("unknown layer", result.stderr)
        self.assertIn("invalid mode", result.stderr)

        plan = subprocess.run(
            [
                sys.executable,
                str(ROUTER),
                "--state",
                str(self.state),
                "--modules-file",
                str(modules_path),
                "plan-json",
                "hello",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(plan.returncode, 0)
        self.assertIn("triggers must contain only non-empty strings", plan.stderr)
        self.assertNotIn("Traceback", plan.stderr)

    def test_plan_rejects_corrupt_profile_shape_without_traceback(self) -> None:
        self.state.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "catalog": "corrupt",
                    "conflicts": [],
                    "bindings": {},
                    "resolutions": {},
                    "preferences": {"disabled_skills": [], "preferred_paths": {}},
                    "feedback": {},
                    "history": [],
                }
            ),
            encoding="utf-8",
        )

        result = self.cli("plan-json", "write a post", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("catalog must be a list", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_feedback_changes_tie_breaking_without_rewriting_route_pack(self) -> None:
        description = "Use when reviewing prose for clarity, structure, tone, and concise language."
        write_skill(self.skill_root, "alpha-editor", description)
        write_skill(self.skill_root, "beta-editor", description)
        self.initialize()
        prompt = "Review this prose for clarity structure tone and concise language"
        before = self.route(prompt)
        self.assertEqual(before["selected_skills"][0]["name"], "alpha-editor")

        self.cli("feedback", "--skill", "beta-editor", "--outcome", "success", "--prompt", prompt)
        self.cli("feedback", "--skill", "beta-editor", "--outcome", "success", "--prompt", prompt)
        after = self.route(prompt)

        self.assertEqual(after["selected_skills"][0]["name"], "beta-editor")

        unrelated = self.route("What is the capital of France?")
        self.assertEqual(unrelated["route_kind"], "abstain")
        self.assertNotIn("beta-editor", [item["name"] for item in unrelated["selected_skills"]])

    def test_ambiguous_near_miss_does_not_route_newsletter_parser_to_content(self) -> None:
        write_skill(
            self.skill_root,
            "test-driven-development",
            "Use when implementing unit tests, regression tests, parsers, and testable software behavior.",
        )
        self.initialize()

        plan = self.route("Write unit tests for a newsletter parser and fix its failing edge cases")

        self.assertNotEqual(plan.get("recommended_module"), "content")
        self.assertIn("test-driven-development", [item["name"] for item in plan["selected_skills"]])

    def test_word_boundaries_and_negation_prevent_substring_false_positives(self) -> None:
        write_skill(self.skill_root, "api", "Use when implementing API endpoints and backend services.")
        self.initialize()

        capital = self.route("What is the capital of France?")
        no_deploy = self.route("Do not deploy anything; only explain the release checklist.")
        commit_only = self.route("Commit the verified local changes but do not deploy anything")

        self.assertEqual(capital["route_kind"], "abstain")
        self.assertNotEqual((no_deploy.get("domain_plan") or {}).get("recommended_pipeline"), "release_pr_deploy")
        self.assertEqual(commit_only.get("recommended_module"), "coding")
        self.assertEqual(commit_only["domain_plan"]["recommended_pipeline"], "release_pr_deploy")
        release_stage = next(
            stage
            for step in commit_only["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "release"
        )
        self.assertNotIn("deploy-to-vercel", release_stage["resolution"].get("missing", []))

    def test_http_router_is_a_coding_task_not_router_catalog_management(self) -> None:
        self.initialize()

        plan = self.route("Build an HTTP router with middleware and unit tests")

        self.assertNotEqual(plan["route_kind"], "management")
        self.assertEqual(plan.get("recommended_module"), "coding")

    def test_http_post_and_full_page_screenshot_are_disambiguated(self) -> None:
        self.initialize()

        endpoint = self.route("Add a POST endpoint to the API and include unit tests")
        screenshot = self.route("Create a shareable full-page screenshot of this prototype")

        self.assertEqual(endpoint.get("recommended_module"), "coding")
        self.assertEqual(screenshot.get("recommended_module"), "content")
        self.assertEqual(screenshot["domain_plan"]["recommended_pipeline"], "visual_asset_package")

    def test_cross_domain_request_returns_both_route_packs(self) -> None:
        self.initialize()

        plan = self.route("Build a React content calendar web app and write the launch post")

        self.assertEqual(set(plan["recommended_modules"]), {"coding", "content"})
        self.assertEqual(plan["route_kind"], "composed_pipeline")

    def test_refresh_preserves_temporarily_missing_manual_binding(self) -> None:
        skill_file = write_skill(
            self.skill_root,
            "private-title-tool",
            "Use when creating editorial titles and opening hooks.",
        )
        self.initialize()
        self.cli("bind", "--module", "content", "--stage", "title_hook", "--skill", "private-title-tool")

        skill_file.unlink()
        self.cli("refresh", "--json")
        missing_profile = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(missing_profile["bindings"]["content:title_hook"]["manual"], ["private-title-tool"])

        write_skill(
            self.skill_root,
            "private-title-tool",
            "Use when creating editorial titles and opening hooks.",
        )
        self.cli("refresh", "--json")
        restored = self.route("生成一套小红书图文笔记，包含标题、正文和封面")
        title_stage = next(
            stage
            for step in restored["domain_plan"]["steps"]
            for stage in step["stages"]
            if stage["stage"] == "title_hook"
        )
        self.assertEqual(title_stage["resolution"]["selected"][0]["name"], "private-title-tool")

    def test_concurrent_feedback_updates_are_serialized(self) -> None:
        write_skill(self.skill_root, "private-editor", "Use when editing prose for clarity and tone.")
        self.initialize()
        commands = [
            [
                sys.executable,
                str(ROUTER),
                "--state",
                str(self.state),
                "feedback",
                "--skill",
                "private-editor",
                "--outcome",
                "success",
            ]
            for _ in range(8)
        ]
        processes = [subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for command in commands]
        results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]

        self.assertTrue(all(returncode == 0 for _, _, returncode in results), results)
        profile = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(profile["feedback"]["private-editor"]["success"], 8)


class InstallerStateTests(unittest.TestCase):
    def run_installer(
        self,
        target: Path,
        *,
        modules: str = "all",
        installer: Path = INSTALLER,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(installer),
                "--target",
                str(target),
                "--modules",
                modules,
                "--no-default-scan-roots",
            ],
            cwd=installer.parents[1],
            text=True,
            capture_output=True,
            check=check,
        )

    def copied_installer(self, destination: Path) -> Path:
        checkout = destination / "source"
        (checkout / "scripts").mkdir(parents=True)
        shutil.copy2(INSTALLER, checkout / "scripts" / "install.py")
        shutil.copytree(
            ROOT / "skills",
            checkout / "skills",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return checkout / "scripts" / "install.py"

    def load_installer_module(self):
        spec = importlib.util.spec_from_file_location("installer_under_test", INSTALLER)
        if spec is None or spec.loader is None:
            raise AssertionError(f"Unable to load installer module from {INSTALLER}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_install_initializes_profile_and_upgrade_preserves_resolutions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-install-") as tmp:
            base = Path(tmp)
            target = base / "installed"
            local = base / "local"
            write_skill(local, "private-writer", "Use when drafting private team updates.")
            command = [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(target),
                "--modules",
                "main,content",
                "--no-default-scan-roots",
                "--scan-root",
                str(local),
            ]
            subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
            state = target / ".skill-routing" / "profile.json"
            profile = json.loads(state.read_text(encoding="utf-8"))
            self.assertIn("private-writer", {item["name"] for item in profile["catalog"]})

            installed_router = target / "skill-routing" / "scripts" / "router_modules.py"
            subprocess.run(
                [
                    sys.executable,
                    str(installed_router),
                    "resolve",
                    "--module",
                    "content",
                    "--stage",
                    "title_hook",
                    "--skill",
                    "hook-generator",
                    "--action",
                    "fallback",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
            upgraded = json.loads(state.read_text(encoding="utf-8"))
            key = "content:title_hook:hook-generator"
            self.assertEqual(upgraded["resolutions"][key]["action"], "fallback")

    def test_reinstall_backs_up_existing_package_and_preserves_custom_module_registration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-upgrade-") as tmp:
            base = Path(tmp)
            target = base / "installed"
            command = [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(target),
                "--modules",
                "main",
                "--no-default-scan-roots",
            ]
            subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
            extension = target / "skill-routing" / "user-extension.txt"
            extension.write_text("keep me in the backup\n", encoding="utf-8")
            registry_path = target / "skill-routing" / "references" / "router-modules.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["modules"].append(
                {
                    "id": "custom",
                    "label": "Custom Router",
                    "skill_name": "custom-router",
                    "skill_path": "../custom-router",
                    "registry_path": "../custom-router/references/pipeline-registry.json",
                    "enabled": False,
                    "domains": ["custom"],
                }
            )
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)

            upgraded_registry = json.loads(registry_path.read_text(encoding="utf-8"))
            self.assertIn("custom", {item["id"] for item in upgraded_registry["modules"]})
            backups = list((target / ".skill-routing" / "backups").rglob("user-extension.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "keep me in the backup\n")

    def test_reinstall_rejects_enabled_custom_module_with_missing_registry_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-bad-custom-module-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            marker = target / "skill-routing" / "preexisting-marker.txt"
            marker.write_text("keep live package\n", encoding="utf-8")
            registry_path = target / "skill-routing" / "references" / "router-modules.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["modules"].append(
                {
                    "id": "custom",
                    "label": "Custom Router",
                    "skill_name": "custom-router",
                    "skill_path": "../custom-router",
                    "registry_path": "../custom-router/references/pipeline-registry.json",
                    "enabled": True,
                    "domains": ["custom"],
                }
            )
            registry_path.write_text(json.dumps(registry), encoding="utf-8")

            result = self.run_installer(target, modules="main", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("custom module", (result.stdout + result.stderr).lower())
            self.assertIn("missing", (result.stdout + result.stderr).lower())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep live package\n")

    def test_failed_install_does_not_restore_over_concurrent_state_feedback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-concurrent-install-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            state = target / ".skill-routing" / "profile.json"
            router = target / "skill-routing" / "scripts" / "router_modules.py"
            installer = self.load_installer_module()

            def concurrent_feedback_then_fail(*_args):
                subprocess.run(
                    [
                        sys.executable,
                        str(router),
                        "--state",
                        str(state),
                        "feedback",
                        "--skill",
                        "skill-routing",
                        "--outcome",
                        "success",
                        "--prompt",
                        "concurrent feedback",
                    ],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                raise RuntimeError("forced install failure")

            argv = [
                "install.py",
                "--target",
                str(target),
                "--modules",
                "main",
                "--no-default-scan-roots",
            ]
            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(installer, "initialize_state", side_effect=concurrent_feedback_then_fail):
                    with self.assertRaises(RuntimeError):
                        installer.main()

            profile = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(profile["feedback"]["skill-routing"]["success"], 1)

    def test_installer_rejects_any_target_inside_source_tree(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--target",
                str(ROOT / "skills" / "skill-routing" / "nested-target"),
                "--modules",
                "main",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source tree", result.stdout + result.stderr)

    def test_reinstall_does_not_index_control_backups_as_effective_router_skills(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-scan-isolation-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target)
            self.run_installer(target)

            profile = json.loads((target / ".skill-routing" / "profile.json").read_text(encoding="utf-8"))
            router_names = {"skill-routing", "content-skill-routing", "coding-skill-routing"}
            routers = {item["name"]: item for item in profile["catalog"] if item["name"] in router_names}

            self.assertEqual(set(routers), router_names)
            for name in router_names:
                self.assertEqual(Path(routers[name]["path"]), (target / name).resolve())
                self.assertNotIn(".skill-routing", Path(routers[name]["path"]).parts)
            self.assertFalse(router_names & {item["name"] for item in profile["conflicts"]})

    def test_staging_validates_skill_scripts_and_registries_before_replacement(self) -> None:
        def downgrade_content_registry(source: Path) -> None:
            registry = source / "skills" / "content-skill-routing" / "references" / "pipeline-registry.json"
            data = json.loads(registry.read_text(encoding="utf-8"))
            data["version"] = 2
            registry.write_text(json.dumps(data), encoding="utf-8")

        def add_invalid_nested_script(source: Path) -> None:
            script = source / "skills" / "skill-routing" / "scripts" / "helpers" / "broken.py"
            script.parent.mkdir()
            script.write_text("def broken(:\n", encoding="utf-8")

        corruptions = {
            "main-skill": lambda source: (source / "skills" / "skill-routing" / "SKILL.md").write_text(
                "# missing frontmatter\n",
                encoding="utf-8",
            ),
            "main-registry": lambda source: (
                source / "skills" / "skill-routing" / "references" / "router-modules.json"
            ).write_text("{not valid json\n", encoding="utf-8"),
            "nested-main-script": add_invalid_nested_script,
            "content-script": lambda source: (
                source / "skills" / "content-skill-routing" / "scripts" / "router_registry.py"
            ).write_text("def broken(:\n", encoding="utf-8"),
            "content-registry-version": downgrade_content_registry,
            "coding-registry": lambda source: (
                source / "skills" / "coding-skill-routing" / "references" / "pipeline-registry.json"
            ).write_text("{not valid json\n", encoding="utf-8"),
        }

        with tempfile.TemporaryDirectory(prefix="skill-routing-stage-validation-") as tmp:
            base = Path(tmp)
            for label, corrupt in corruptions.items():
                with self.subTest(asset=label):
                    scenario = base / label
                    target = scenario / "installed"
                    self.run_installer(target)
                    marker = target / "skill-routing" / "preexisting-marker.txt"
                    marker.write_text("preserve existing install\n", encoding="utf-8")
                    registry = target / "skill-routing" / "references" / "router-modules.json"
                    registry_before = registry.read_bytes()
                    installer = self.copied_installer(scenario)
                    corrupt(installer.parents[1])

                    result = self.run_installer(target, installer=installer, check=False)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("staged package validation", (result.stdout + result.stderr).lower())
                    self.assertEqual(marker.read_text(encoding="utf-8"), "preserve existing install\n")
                    self.assertEqual(registry.read_bytes(), registry_before)
                    backup_root = target / ".skill-routing" / "backups"
                    self.assertFalse(backup_root.exists() and any(backup_root.iterdir()))

    def test_subset_install_moves_unselected_bundled_pack_to_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-subset-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target)
            marker = target / "content-skill-routing" / "content-marker.txt"
            marker.write_text("old content package\n", encoding="utf-8")

            self.run_installer(target, modules="main,coding")

            self.assertFalse((target / "content-skill-routing").exists())
            registry = json.loads(
                (target / "skill-routing" / "references" / "router-modules.json").read_text(encoding="utf-8")
            )
            self.assertEqual({item["id"] for item in registry["modules"]}, {"coding"})
            backups = list((target / ".skill-routing" / "backups").rglob("content-marker.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "old content package\n")

    def test_failed_subset_install_restores_removed_pack_and_cleans_transaction_backup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-subset-rollback-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target)
            marker = target / "content-skill-routing" / "content-marker.txt"
            marker.write_text("restore me\n", encoding="utf-8")
            state = target / ".skill-routing" / "profile.json"
            state_before = state.read_bytes()
            registry = target / "skill-routing" / "references" / "router-modules.json"
            registry_before = registry.read_bytes()
            state.with_suffix(".json.lock").write_text("held by test\n", encoding="utf-8")

            result = self.run_installer(target, modules="main,coding", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "restore me\n")
            self.assertEqual(state.read_bytes(), state_before)
            self.assertEqual(registry.read_bytes(), registry_before)
            backup_root = target / ".skill-routing" / "backups"
            self.assertFalse(backup_root.exists() and any(backup_root.iterdir()))

    def test_keyboard_interrupt_after_replacement_rolls_back_packages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-interrupt-rollback-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            marker = target / "skill-routing" / "preexisting-marker.txt"
            marker.write_text("restore after interrupt\n", encoding="utf-8")
            registry = target / "skill-routing" / "references" / "router-modules.json"
            registry_before = registry.read_bytes()
            installer = self.load_installer_module()
            argv = [
                str(INSTALLER),
                "--target",
                str(target),
                "--modules",
                "main",
                "--no-default-scan-roots",
            ]

            with mock.patch.object(installer, "initialize_state", side_effect=KeyboardInterrupt):
                with mock.patch.object(sys, "argv", argv):
                    with self.assertRaises(KeyboardInterrupt):
                        installer.main()

            self.assertEqual(marker.read_text(encoding="utf-8"), "restore after interrupt\n")
            self.assertEqual(registry.read_bytes(), registry_before)
            backup_root = target / ".skill-routing" / "backups"
            self.assertFalse(backup_root.exists() and any(backup_root.iterdir()))

    def test_keyboard_interrupt_during_package_moves_uses_local_rollback_journal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-move-interrupt-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target)
            marker = target / "skill-routing" / "preexisting-marker.txt"
            marker.write_text("restore partial move\n", encoding="utf-8")
            installer = self.load_installer_module()
            real_move = installer.shutil.move
            calls = 0

            def interrupt_second_move(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt
                return real_move(source, destination)

            argv = [
                str(INSTALLER),
                "--target",
                str(target),
                "--modules",
                "all",
                "--no-default-scan-roots",
            ]
            with mock.patch.object(installer.shutil, "move", side_effect=interrupt_second_move):
                with mock.patch.object(sys, "argv", argv):
                    with self.assertRaises(KeyboardInterrupt):
                        installer.main()

            self.assertEqual(marker.read_text(encoding="utf-8"), "restore partial move\n")
            for package in ("skill-routing", "content-skill-routing", "coding-skill-routing"):
                self.assertTrue((target / package).is_dir())
            backup_root = target / ".skill-routing" / "backups"
            self.assertFalse(backup_root.exists() and any(backup_root.iterdir()))

    def test_stale_mtime_does_not_steal_lock_from_live_installer_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-live-lock-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            marker = target / "skill-routing" / "preexisting-marker.txt"
            marker.write_text("live owner keeps package\n", encoding="utf-8")
            lock = target / ".skill-routing" / "install.lock"
            lock_payload = f"pid={os.getpid()}\ntoken=live-test-owner\n"
            lock.write_text(lock_payload, encoding="utf-8")
            old = lock.stat().st_mtime - 600
            os.utime(lock, (old, old))

            result = self.run_installer(target, modules="main", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("active", (result.stdout + result.stderr).lower())
            self.assertEqual(lock.read_text(encoding="utf-8"), lock_payload)
            self.assertEqual(marker.read_text(encoding="utf-8"), "live owner keeps package\n")

    def test_scan_root_partition_fails_closed_when_control_parent_is_unreadable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-scan-fail-closed-") as tmp:
            base = Path(tmp)
            target = base / "installed"
            target.mkdir()
            installer = self.load_installer_module()

            with mock.patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
                roots = installer.split_scan_root_around_control(base, target / ".skill-routing")

            self.assertEqual(roots, [])

    def test_windows_process_probe_fails_closed_without_calling_os_kill(self) -> None:
        installer = self.load_installer_module()
        with mock.patch.object(installer.os, "name", "nt"):
            with mock.patch.object(installer.os, "kill") as kill:
                alive = installer.process_is_alive(999_999)

        self.assertTrue(alive)
        kill.assert_not_called()

    def test_malformed_existing_main_registry_aborts_without_replacing_packages(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-bad-existing-registry-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            marker = target / "skill-routing" / "preexisting-marker.txt"
            marker.write_text("do not replace\n", encoding="utf-8")
            registry = target / "skill-routing" / "references" / "router-modules.json"
            malformed = b'{"modules": [invalid]\n'
            registry.write_bytes(malformed)

            result = self.run_installer(target, modules="main", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing main registry", (result.stdout + result.stderr).lower())
            self.assertEqual(registry.read_bytes(), malformed)
            self.assertEqual(marker.read_text(encoding="utf-8"), "do not replace\n")
            backup_root = target / ".skill-routing" / "backups"
            self.assertFalse(backup_root.exists() and any(backup_root.iterdir()))

    def test_dry_run_validates_existing_target_instead_of_false_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-dry-run-invalid-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            registry = target / "skill-routing" / "references" / "router-modules.json"
            registry.write_text('{"modules": [invalid]\n', encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--target",
                    str(target),
                    "--modules",
                    "main",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("existing main registry", (result.stdout + result.stderr).lower())

    def test_installer_rejects_symlinked_control_directory_without_touching_victim(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-control-symlink-") as tmp:
            base = Path(tmp)
            target = base / "installed"
            target.mkdir()
            victim = base / "victim"
            victim.mkdir()
            sentinel = victim / "sentinel.txt"
            sentinel.write_text("untouched\n", encoding="utf-8")
            try:
                (target / ".skill-routing").symlink_to(victim, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks are unavailable: {exc}")

            result = self.run_installer(target, modules="main", check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", (result.stdout + result.stderr).lower())
            self.assertEqual(list(victim.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched\n")

    def test_installer_rejects_symlinked_control_children_before_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-child-symlink-") as tmp:
            base = Path(tmp)
            for component in ("backups", "staging", "profile.json"):
                with self.subTest(component=component):
                    scenario = base / component.replace(".", "-")
                    target = scenario / "installed"
                    self.run_installer(target, modules="main")
                    marker = target / "skill-routing" / "preexisting-marker.txt"
                    marker.write_text("preserve live package\n", encoding="utf-8")
                    control_path = target / ".skill-routing" / component
                    if control_path.exists() or control_path.is_symlink():
                        if control_path.is_dir() and not control_path.is_symlink():
                            shutil.rmtree(control_path)
                        else:
                            control_path.unlink()
                    victim = scenario / "victim"
                    if component == "profile.json":
                        victim.parent.mkdir(parents=True, exist_ok=True)
                        victim.write_text("external state\n", encoding="utf-8")
                    else:
                        victim.mkdir(parents=True)
                        (victim / "sentinel.txt").write_text("external directory\n", encoding="utf-8")
                    try:
                        control_path.symlink_to(victim, target_is_directory=component != "profile.json")
                    except OSError as exc:
                        self.skipTest(f"symlinks are unavailable: {exc}")

                    result = self.run_installer(target, modules="main", check=False)

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("symlink", (result.stdout + result.stderr).lower())
                    self.assertEqual(marker.read_text(encoding="utf-8"), "preserve live package\n")
                    if component == "profile.json":
                        self.assertEqual(victim.read_text(encoding="utf-8"), "external state\n")
                    else:
                        self.assertEqual(
                            (victim / "sentinel.txt").read_text(encoding="utf-8"),
                            "external directory\n",
                        )

    def test_backup_pruning_preserves_unmanaged_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-routing-unmanaged-backups-") as tmp:
            target = Path(tmp) / "installed"
            self.run_installer(target, modules="main")
            backup_root = target / ".skill-routing" / "backups"
            for index in range(7):
                unmanaged = backup_root / f"user-backup-{index}"
                unmanaged.mkdir(parents=True)
                (unmanaged / "sentinel.txt").write_text(f"user data {index}\n", encoding="utf-8")
            malformed = backup_root / "looks-managed-but-is-not"
            malformed.mkdir()
            (malformed / ".skill-routing-backup.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "created_by": "skill-routing-installer",
                        "backup_id": malformed.name,
                        "packages": [{}],
                    }
                ),
                encoding="utf-8",
            )
            (malformed / "sentinel.txt").write_text("malformed manifest must be preserved\n", encoding="utf-8")

            self.run_installer(target, modules="main")

            for index in range(7):
                sentinel = backup_root / f"user-backup-{index}" / "sentinel.txt"
                self.assertEqual(sentinel.read_text(encoding="utf-8"), f"user data {index}\n")
            self.assertEqual(
                (malformed / "sentinel.txt").read_text(encoding="utf-8"),
                "malformed manifest must be preserved\n",
            )


if __name__ == "__main__":
    unittest.main()
