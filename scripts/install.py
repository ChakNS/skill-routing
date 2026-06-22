#!/usr/bin/env python3
"""Install the routing skill matrix and generate local skill profiles."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
ROUTER_SKILLS = {
    "main": "skill-routing",
    "content": "content-skill-routing",
    "coding": "coding-skill-routing",
}
DEFAULT_SCAN_ROOTS = [
    Path("~/.codex/skills"),
    Path("~/.claude/skills"),
    Path("~/.cc-switch/skills"),
    Path("~/AISkills"),
]


def parse_modules(raw: str) -> list[str]:
    raw = raw.strip()
    if raw == "all":
        return ["main", "content", "coding"]
    modules = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in modules if item not in ROUTER_SKILLS]
    if unknown:
        raise SystemExit(f"Unknown module(s): {', '.join(unknown)}")
    if "main" not in modules:
        modules.insert(0, "main")
    return modules


def parse_skill_name(skill_file: Path) -> str | None:
    text = skill_file.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return skill_file.parent.name
    match = re.search(r"^name:\s*([A-Za-z0-9_.:-]+)\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else skill_file.parent.name


def discover_skills(scan_roots: list[Path]) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for root in scan_roots:
        expanded = root.expanduser()
        if not expanded.exists():
            continue
        for skill_file in expanded.glob("*/SKILL.md"):
            name = parse_skill_name(skill_file)
            if name and name not in discovered:
                discovered[name] = str(skill_file.parent.resolve())
    return discovered


def copy_skill(skill_name: str, target: Path) -> Path:
    src = SKILLS_ROOT / skill_name
    dest = target / skill_name
    if not src.exists():
        raise SystemExit(f"Missing source skill: {src}")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def validate_target(target: Path) -> Path:
    resolved = target.expanduser().resolve()
    source_root = SKILLS_ROOT.resolve()
    if resolved == source_root:
        raise SystemExit(f"Refusing to install into the source skills directory: {resolved}")
    if resolved == Path(resolved.anchor):
        raise SystemExit(f"Refusing to install into filesystem root: {resolved}")
    return resolved


def load_registry(skill_dir: Path) -> dict[str, Any]:
    path = skill_dir / "references" / "pipeline-registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_main_module_registry(target: Path, modules: list[str]) -> None:
    installed_modules: list[dict[str, Any]] = []
    if "content" in modules:
        installed_modules.append(
            {
                "id": "content",
                "label": "Content Skill Routing",
                "skill_name": "content-skill-routing",
                "skill_path": str((target / "content-skill-routing").resolve()),
                "registry_path": str((target / "content-skill-routing" / "references" / "pipeline-registry.json").resolve()),
                "enabled": True,
                "domains": [
                    "content",
                    "research",
                    "writing",
                    "visual packaging",
                    "manual publish handoff",
                    "creator systems",
                ],
            }
        )
    if "coding" in modules:
        installed_modules.append(
            {
                "id": "coding",
                "label": "Coding Skill Routing",
                "skill_name": "coding-skill-routing",
                "skill_path": str((target / "coding-skill-routing").resolve()),
                "registry_path": str((target / "coding-skill-routing" / "references" / "pipeline-registry.json").resolve()),
                "enabled": True,
                "domains": [
                    "programming",
                    "software engineering",
                    "frontend",
                    "backend",
                    "debugging",
                    "testing",
                    "deployment",
                    "skill tooling",
                ],
            }
        )
    data = {"version": 1, "main_router": "skill-routing", "modules": installed_modules}
    out = target / "skill-routing" / "references" / "router-modules.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_profile(skill_dir: Path, discovered: dict[str, str], scan_roots: list[Path]) -> dict[str, Any]:
    registry = load_registry(skill_dir)
    recommended = []
    for skill in registry.get("skills", []):
        name = skill["name"]
        recommended.append(
            {
                "name": name,
                "installed": name in discovered,
                "installed_path": discovered.get(name),
                "priority": skill.get("priority", "normal"),
                "category": skill.get("category", ""),
                "layer": skill.get("layer", ""),
                "parallel_safe": skill.get("parallel_safe", False),
                "stages": skill.get("stages", []),
                "use_when": skill.get("use_when", ""),
                "install_hint": skill.get("install_hint", ""),
            }
        )
    missing = [item["name"] for item in recommended if not item["installed"]]
    return {
        "generated_by": "skill-routing/scripts/install.py",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "router": registry.get("router"),
        "scan_roots": [str(root.expanduser()) for root in scan_roots],
        "installed_skill_count": len(discovered),
        "recommended_skills": recommended,
        "missing_recommendations": missing,
        "note": "Downstream skills are recommendations. The router remains usable when these are missing.",
    }


def write_domain_profiles(target: Path, modules: list[str], discovered: dict[str, str], scan_roots: list[Path]) -> None:
    for module in ("content", "coding"):
        if module not in modules:
            continue
        skill_dir = target / ROUTER_SKILLS[module]
        profile = build_profile(skill_dir, discovered, scan_roots)
        out = skill_dir / "references" / "local-skill-profile.generated.json"
        out.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="~/.codex/skills", help="Skill install directory.")
    parser.add_argument("--modules", default="all", help="all, main, main,content, or main,coding.")
    parser.add_argument("--scan-root", action="append", default=[], help="Additional skill root to scan.")
    parser.add_argument(
        "--no-default-scan-roots",
        action="store_true",
        help="Only scan roots passed with --scan-root plus the target directory.",
    )
    args = parser.parse_args()

    target = validate_target(Path(args.target))
    modules = parse_modules(args.modules)
    scan_roots = ([] if args.no_default_scan_roots else DEFAULT_SCAN_ROOTS) + [Path(item) for item in args.scan_root]

    target.mkdir(parents=True, exist_ok=True)
    installed_paths = []
    for module in modules:
        installed_paths.append(copy_skill(ROUTER_SKILLS[module], target))

    discovered = discover_skills(scan_roots + [target])
    write_main_module_registry(target, modules)
    write_domain_profiles(target, modules, discovered, scan_roots + [target])

    print("Installed routing skills:")
    for path in installed_paths:
        print(f"- {path}")
    print(f"Discovered existing skills: {len(discovered)}")
    print(f"Main registry: {target / 'skill-routing' / 'references' / 'router-modules.json'}")


if __name__ == "__main__":
    main()
