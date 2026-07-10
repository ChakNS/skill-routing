#!/usr/bin/env python3
"""Safely install route packs and initialize a personal skill catalog."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
ROUTER_SKILLS = {
    "main": "skill-routing",
    "content": "content-skill-routing",
    "coding": "coding-skill-routing",
}
BUILTIN_MODULE_IDS = {"content", "coding"}
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "local-skill-profile.generated.json")
CONTROL_DIRECTORY = ".skill-routing"
BACKUP_DIRECTORY = "backups"
STAGING_DIRECTORY = "staging"
BACKUP_MANIFEST = ".skill-routing-backup.json"
BACKUP_SCHEMA_VERSION = 1
BACKUP_CREATED_BY = "skill-routing-installer"
REQUIRED_PACKAGE_FILES = {
    "skill-routing": {
        "SKILL.md",
        "scripts/router_modules.py",
        "scripts/routing_core.py",
        "scripts/domain_router_cli.py",
        "references/router-modules.json",
        "references/profile.schema.json",
        "references/route-pack.schema.json",
    },
    "content-skill-routing": {
        "SKILL.md",
        "scripts/router_registry.py",
        "references/pipeline-registry.json",
    },
    "coding-skill-routing": {
        "SKILL.md",
        "scripts/router_registry.py",
        "references/pipeline-registry.json",
    },
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def lstat_mode(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except FileNotFoundError:
        return None


def require_real_directory(path: Path, label: str, *, create: bool = False) -> Path:
    mode = lstat_mode(path)
    if mode is None:
        if not create:
            raise SystemExit(f"Missing {label}: {path}")
        path.mkdir(mode=0o700)
        mode = lstat_mode(path)
    if mode is not None and stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing symlinked {label}: {path}")
    if mode is None or not stat.S_ISDIR(mode):
        raise SystemExit(f"Expected {label} to be a directory: {path}")
    return path


def require_regular_file_or_missing(path: Path, label: str) -> None:
    mode = lstat_mode(path)
    if mode is None:
        return
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing symlinked {label}: {path}")
    if not stat.S_ISREG(mode):
        raise SystemExit(f"Expected {label} to be a regular file: {path}")


def prepare_control_layout(target: Path) -> tuple[Path, Path, Path, Path]:
    control = require_real_directory(target / CONTROL_DIRECTORY, "skill-routing control directory", create=True)
    backups = target / CONTROL_DIRECTORY / BACKUP_DIRECTORY
    staging = target / CONTROL_DIRECTORY / STAGING_DIRECTORY
    if lstat_mode(backups) is not None:
        require_real_directory(backups, "skill-routing backup directory")
    require_real_directory(staging, "skill-routing staging directory", create=True)
    state = target / CONTROL_DIRECTORY / "profile.json"
    require_regular_file_or_missing(state, "skill-routing state file")
    require_regular_file_or_missing(state.with_suffix(state.suffix + ".lock"), "skill-routing state lock")
    require_regular_file_or_missing(control / "install.lock", "skill-routing install lock")
    return control, backups, staging, state


def validate_existing_bundled_paths(target: Path) -> None:
    for name in ROUTER_SKILLS.values():
        path = target / name
        mode = lstat_mode(path)
        if mode is None:
            continue
        if stat.S_ISLNK(mode):
            raise SystemExit(f"Refusing symlinked bundled route pack: {path}")
        if not stat.S_ISDIR(mode):
            raise SystemExit(f"Expected bundled route pack to be a directory: {path}")


def parse_modules(raw: str) -> list[str]:
    raw = raw.strip()
    if raw == "all":
        return ["main", "content", "coding"]
    modules = list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    unknown = [item for item in modules if item not in ROUTER_SKILLS]
    if unknown:
        raise SystemExit(f"Unknown module(s): {', '.join(unknown)}")
    if "main" not in modules:
        modules.insert(0, "main")
    return modules


def validate_target(target: Path) -> Path:
    resolved = canonical(target)
    repo = canonical(REPO_ROOT)
    if resolved == Path(resolved.anchor):
        raise SystemExit(f"Refusing to install into filesystem root: {resolved}")
    if resolved == repo or repo in resolved.parents or resolved in repo.parents:
        raise SystemExit(f"Refusing to install into or around the source tree: {resolved}")
    return resolved


def lock_owner_pid(lock: Path) -> int | None:
    try:
        for line in lock.read_text(encoding="utf-8").splitlines():
            if line.startswith("pid="):
                return int(line.removeprefix("pid="))
    except (OSError, UnicodeError, ValueError):
        return None
    return None


def process_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name != "posix":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


@contextmanager
def install_lock(target: Path, stale_after: int = 300) -> Iterator[None]:
    control = require_real_directory(target / CONTROL_DIRECTORY, "skill-routing control directory")
    lock = control / "install.lock"
    mode = lstat_mode(lock)
    if mode is not None and stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing symlinked skill-routing install lock: {lock}")
    if mode is not None and not stat.S_ISREG(mode):
        raise SystemExit(f"Expected skill-routing install lock to be a regular file: {lock}")
    descriptor: int | None = None
    payload = f"pid={os.getpid()}\ntoken={os.urandom(16).hex()}\n".encode()
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        mode = lstat_mode(lock)
        if mode is not None and stat.S_ISLNK(mode):
            raise SystemExit(f"Refusing symlinked skill-routing install lock: {lock}")
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            age = 0
        owner_pid = lock_owner_pid(lock)
        if age > stale_after and (owner_pid is None or not process_is_alive(owner_pid)):
            lock.unlink(missing_ok=True)
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise SystemExit(f"Another skill-routing installation is active: {lock}") from exc
        else:
            raise SystemExit(f"Another skill-routing installation is active: {lock}")
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            if lstat_mode(lock) is not None and not lock.is_symlink() and lock.read_bytes() == payload:
                lock.unlink()
        except OSError:
            pass


@contextmanager
def state_lock(state: Path, stale_after: int = 300, timeout: float = 10.0) -> Iterator[None]:
    lock = state.with_suffix(state.suffix + ".lock")
    mode = lstat_mode(lock)
    if mode is not None and stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing symlinked skill-routing state lock: {lock}")
    if mode is not None and not stat.S_ISREG(mode):
        raise SystemExit(f"Expected skill-routing state lock to be a regular file: {lock}")
    token = os.urandom(16).hex()
    payload = f"pid={os.getpid()}\ntoken={token}\n"
    deadline = time.monotonic() + timeout
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(descriptor, payload.encode())
            os.fsync(descriptor)
            os.close(descriptor)
            break
        except FileExistsError:
            mode = lstat_mode(lock)
            if mode is not None and stat.S_ISLNK(mode):
                raise SystemExit(f"Refusing symlinked skill-routing state lock: {lock}")
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                age = 0
            owner_pid = lock_owner_pid(lock)
            if age > stale_after and (owner_pid is None or not process_is_alive(owner_pid)):
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise SystemExit(f"Timed out waiting for skill-routing state lock: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            current = lock.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
        if f"token={token}" in current:
            lock.unlink(missing_ok=True)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def read_optional_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def snapshot_state(state: Path) -> bytes | None:
    with state_lock(state):
        return read_optional_bytes(state)


def restore_state_if_unchanged(state: Path, snapshot: bytes | None, expected_current: bytes | None) -> bool:
    with state_lock(state):
        current = read_optional_bytes(state)
        if current != expected_current:
            return False
        if snapshot is None:
            state.unlink(missing_ok=True)
        else:
            atomic_write_bytes(state, snapshot)
        return True


def load_existing_custom_modules(target: Path) -> list[dict[str, Any]]:
    main_package = target / "skill-routing"
    registry = target / "skill-routing" / "references" / "router-modules.json"
    if lstat_mode(main_package) is None:
        return []
    mode = lstat_mode(registry)
    if mode is None:
        raise SystemExit(f"Existing main registry is missing: {registry}")
    if stat.S_ISLNK(mode):
        raise SystemExit(f"Refusing symlinked existing main registry: {registry}")
    if not stat.S_ISREG(mode):
        raise SystemExit(f"Existing main registry is not a regular file: {registry}")
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Existing main registry contains invalid JSON: {registry}: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"Unable to read existing main registry: {registry}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("modules"), list):
        raise SystemExit(f"Existing main registry must contain a modules list: {registry}")
    custom_modules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(data["modules"]):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            raise SystemExit(f"Existing main registry module {index} is malformed: {registry}")
        module_id = item["id"]
        if module_id in seen:
            raise SystemExit(f"Existing main registry contains duplicate module id {module_id!r}: {registry}")
        seen.add(module_id)
        if module_id not in BUILTIN_MODULE_IDS:
            if item.get("enabled", True):
                registry_value = item.get("registry_path")
                if not isinstance(registry_value, str) or not registry_value.strip():
                    raise SystemExit(f"Enabled custom module {module_id!r} has no registry_path: {registry}")
                custom_registry = Path(registry_value).expanduser()
                if not custom_registry.is_absolute():
                    custom_registry = main_package / custom_registry
                custom_registry = canonical(custom_registry)
                mode = lstat_mode(custom_registry)
                if mode is None:
                    raise SystemExit(f"Enabled custom module {module_id!r} registry is missing: {custom_registry}")
                if stat.S_ISLNK(mode):
                    raise SystemExit(f"Refusing symlinked custom module registry for {module_id!r}: {custom_registry}")
                if not stat.S_ISREG(mode):
                    raise SystemExit(f"Enabled custom module {module_id!r} registry is not a regular file: {custom_registry}")
                try:
                    custom_data = json.loads(custom_registry.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise SystemExit(f"Enabled custom module {module_id!r} registry is invalid: {custom_registry}: {exc}") from exc
                if not isinstance(custom_data, dict):
                    raise SystemExit(f"Enabled custom module {module_id!r} registry must contain a JSON object: {custom_registry}")
            custom_modules.append(dict(item))
    return custom_modules


def module_record(module: str) -> dict[str, Any]:
    if module == "content":
        return {
            "id": "content",
            "label": "Content Skill Routing",
            "skill_name": "content-skill-routing",
            "skill_path": "../content-skill-routing",
            "registry_path": "../content-skill-routing/references/pipeline-registry.json",
            "enabled": True,
            "domains": ["content", "research", "writing", "visual packaging", "manual publish handoff", "creator systems"],
        }
    if module == "coding":
        return {
            "id": "coding",
            "label": "Coding Skill Routing",
            "skill_name": "coding-skill-routing",
            "skill_path": "../coding-skill-routing",
            "registry_path": "../coding-skill-routing/references/pipeline-registry.json",
            "enabled": True,
            "domains": ["programming", "software engineering", "frontend", "backend", "debugging", "testing", "deployment", "skill tooling"],
        }
    raise ValueError(f"Not a domain module: {module}")


def write_main_module_registry(target: Path, modules: list[str], custom_modules: list[dict[str, Any]]) -> Path:
    builtin = [module_record(module) for module in ("content", "coding") if module in modules]
    data = {
        "version": 2,
        "main_router": "skill-routing",
        "modules": [*builtin, *custom_modules],
    }
    output = target / "skill-routing" / "references" / "router-modules.json"
    atomic_write_json(output, data)
    return output


def stage_packages(modules: list[str], staging: Path) -> None:
    for module in modules:
        name = ROUTER_SKILLS[module]
        source = SKILLS_ROOT / name
        if not (source / "SKILL.md").exists():
            raise SystemExit(f"Missing source skill: {source}")
        shutil.copytree(source, staging / name, ignore=COPY_IGNORE)
    required_core = staging / "skill-routing" / "scripts" / "routing_core.py"
    if not required_core.exists():
        raise SystemExit(f"Staged package is incomplete: {required_core}")


def skill_frontmatter(skill_file: Path) -> dict[str, str]:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing YAML frontmatter")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("unterminated YAML frontmatter") from exc
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        metadata[key.strip()] = value
    return metadata


def validate_staged_packages(modules: list[str], staging: Path) -> None:
    errors: list[str] = []
    selected_names = [ROUTER_SKILLS[module] for module in modules]
    for name in selected_names:
        package = staging / name
        for relative in sorted(REQUIRED_PACKAGE_FILES[name]):
            path = package / relative
            mode = lstat_mode(path)
            if mode is None:
                errors.append(f"{name}: missing {relative}")
            elif stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                errors.append(f"{name}: {relative} must be a regular file")

        skill_file = package / "SKILL.md"
        if skill_file.is_file() and not skill_file.is_symlink():
            try:
                metadata = skill_frontmatter(skill_file)
                if metadata.get("name") != name:
                    errors.append(f"{name}: SKILL.md name must be {name!r}")
                if not metadata.get("description"):
                    errors.append(f"{name}: SKILL.md description is required")
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append(f"{name}: invalid SKILL.md: {exc}")

        scripts = sorted((package / "scripts").rglob("*.py"))
        if not scripts:
            errors.append(f"{name}: no Python scripts found")
        for script in scripts:
            try:
                ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
            except (OSError, UnicodeError, SyntaxError) as exc:
                errors.append(f"{name}: invalid script {script.name}: {exc}")

        for registry in sorted((package / "references").rglob("*.json")):
            try:
                data = json.loads(registry.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    errors.append(f"{name}: {registry.name} must contain a JSON object")
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                errors.append(f"{name}: invalid registry {registry.name}: {exc}")

    if not errors:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        entrypoints = [staging / name / "scripts" / ("router_modules.py" if name == "skill-routing" else "router_registry.py") for name in selected_names]
        for entrypoint in entrypoints:
            result = subprocess.run(
                [sys.executable, "-B", str(entrypoint), "--help"],
                cwd=staging,
                text=True,
                capture_output=True,
                timeout=30,
                env=environment,
            )
            if result.returncode != 0:
                errors.append(f"{entrypoint.parent.parent.name}: script import failed: {result.stderr or result.stdout}")

    if not errors:
        write_main_module_registry(staging, modules, [])
        router = staging / "skill-routing" / "scripts" / "router_modules.py"
        registry = staging / "skill-routing" / "references" / "router-modules.json"
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(router),
                "--modules-file",
                str(registry),
                "--state",
                str(staging / ".validation-profile.json"),
                "validate",
            ],
            cwd=staging,
            text=True,
            capture_output=True,
            timeout=30,
            env=environment,
        )
        if result.returncode != 0:
            errors.append(f"route-pack registry validation failed: {result.stderr or result.stdout}")

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"Staged package validation failed:\n{details}")


def create_backup_directory(target: Path) -> Path:
    root = target / CONTROL_DIRECTORY / BACKUP_DIRECTORY
    require_real_directory(root, "skill-routing backup directory", create=True)
    backup = Path(tempfile.mkdtemp(prefix=f"{utc_stamp()}-", dir=root))
    packages = [
        name
        for name in ROUTER_SKILLS.values()
        if lstat_mode(target / name) is not None
    ]
    atomic_write_json(
        backup / BACKUP_MANIFEST,
        {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_by": BACKUP_CREATED_BY,
            "backup_id": backup.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "packages": packages,
        },
    )
    return backup


def is_managed_backup(path: Path) -> bool:
    mode = lstat_mode(path)
    if mode is None or stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        return False
    manifest = path / BACKUP_MANIFEST
    manifest_mode = lstat_mode(manifest)
    if manifest_mode is None or stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode):
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    packages = data.get("packages")
    return (
        data.get("schema_version") == BACKUP_SCHEMA_VERSION
        and data.get("created_by") == BACKUP_CREATED_BY
        and data.get("backup_id") == path.name
        and isinstance(packages, list)
        and all(isinstance(package, str) for package in packages)
        and len(packages) == len(set(packages))
        and all(package in ROUTER_SKILLS.values() for package in packages)
    )


def cleanup_empty_backup(path: Path | None) -> None:
    if path is None or not is_managed_backup(path):
        return
    remaining = [item for item in path.iterdir() if item.name != BACKUP_MANIFEST]
    if remaining:
        return
    (path / BACKUP_MANIFEST).unlink()
    path.rmdir()


def replace_packages(target: Path, modules: list[str], staging: Path, backup: Path) -> tuple[list[Path], list[tuple[Path, Path]]]:
    installed: list[Path] = []
    moved_backups: list[tuple[Path, Path]] = []
    try:
        for name in ROUTER_SKILLS.values():
            destination = target / name
            if destination.exists() or destination.is_symlink():
                backup_destination = backup / name
                backup_destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(backup_destination))
                moved_backups.append((destination, backup_destination))
        for module in modules:
            name = ROUTER_SKILLS[module]
            destination = target / name
            staged = staging / name
            os.replace(staged, destination)
            installed.append(destination)
    except BaseException:
        for destination in reversed(installed):
            if destination.exists() or destination.is_symlink():
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination)
                else:
                    destination.unlink(missing_ok=True)
        for destination, backup_destination in reversed(moved_backups):
            if backup_destination.exists():
                shutil.move(str(backup_destination), str(destination))
        raise
    return installed, moved_backups


def rollback_packages(installed: list[Path], moved_backups: list[tuple[Path, Path]]) -> None:
    for destination in reversed(installed):
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink(missing_ok=True)
    for destination, backup_destination in reversed(moved_backups):
        if backup_destination.exists():
            shutil.move(str(backup_destination), str(destination))


def default_scan_roots(cwd: Path | None = None) -> list[Path]:
    current = canonical(cwd or Path.cwd())
    project_roots: list[Path] = []
    cursor = current
    while True:
        project_roots.extend([cursor / ".agents" / "skills", cursor / ".claude" / "skills"])
        if cursor.parent == cursor or (cursor / ".git").exists():
            break
        cursor = cursor.parent
    return [
        *project_roots,
        Path("~/.agents/skills"),
        Path("~/.claude/skills"),
        Path("~/.codex/skills"),
        Path("~/.cc-switch/skills"),
        Path("~/AISkills"),
    ]


def split_scan_root_around_control(root: Path, control: Path) -> list[Path]:
    root = canonical(root)
    control = canonical(control)
    if root == control or control in root.parents:
        return []
    if root not in control.parents:
        return [root]
    if not root.exists() or not root.is_dir():
        return []
    result: list[Path] = []
    try:
        children = sorted(root.iterdir(), key=lambda item: str(item).casefold())
    except OSError:
        return []
    for child in children:
        if child.is_dir():
            result.extend(split_scan_root_around_control(child, control))
    return result


def safe_scan_roots(target: Path, scan_roots: list[Path], include_defaults: bool) -> list[Path]:
    control = target / CONTROL_DIRECTORY
    requested = [target, *scan_roots]
    if include_defaults:
        requested.extend(default_scan_roots())
    result: list[Path] = []
    seen: set[str] = set()
    for requested_root in requested:
        for root in split_scan_root_around_control(requested_root, control):
            key = os.path.normcase(str(canonical(root)))
            if key not in seen:
                seen.add(key)
                result.append(canonical(root))
    return result


def initialize_state(target: Path, scan_roots: list[Path], no_default_scan_roots: bool) -> None:
    router = target / "skill-routing" / "scripts" / "router_modules.py"
    state = target / CONTROL_DIRECTORY / "profile.json"
    roots = safe_scan_roots(target, scan_roots, include_defaults=not no_default_scan_roots)
    command = [sys.executable, "-B", str(router), "--state", str(state), "init"]
    for root in roots:
        command.extend(["--scan-root", str(root)])
    command.append("--no-default-scan-roots")
    command.append("--json")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(command, text=True, capture_output=True, timeout=120, env=environment)
    if result.returncode != 0:
        raise RuntimeError(f"Installed router initialization failed:\n{result.stderr or result.stdout}")


def validate_existing_registry(target: Path) -> None:
    router = target / "skill-routing" / "scripts" / "router_modules.py"
    registry = target / "skill-routing" / "references" / "router-modules.json"
    if lstat_mode(router) is None or lstat_mode(registry) is None:
        return
    validation_state = target / CONTROL_DIRECTORY / ".existing-registry-validation-profile.json"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(router),
            "--modules-file",
            str(registry),
            "--state",
            str(validation_state),
            "validate",
        ],
        text=True,
        capture_output=True,
        timeout=30,
        env=environment,
    )
    validation_state.unlink(missing_ok=True)
    validation_state.with_suffix(validation_state.suffix + ".lock").unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit(f"Existing route-pack registry validation failed:\n{result.stderr or result.stdout}")


def validate_installed_registry(target: Path, registry: Path) -> None:
    router = target / "skill-routing" / "scripts" / "router_modules.py"
    validation_state = target / CONTROL_DIRECTORY / ".install-validation-profile.json"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(router),
            "--modules-file",
            str(registry),
            "--state",
            str(validation_state),
            "validate",
        ],
        text=True,
        capture_output=True,
        timeout=30,
        env=environment,
    )
    validation_state.unlink(missing_ok=True)
    validation_state.with_suffix(validation_state.suffix + ".lock").unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"Installed route-pack registry validation failed:\n{result.stderr or result.stdout}")


def prune_empty_or_old_backups(target: Path, keep: int = 5) -> None:
    root = target / CONTROL_DIRECTORY / BACKUP_DIRECTORY
    if lstat_mode(root) is None:
        return
    require_real_directory(root, "skill-routing backup directory")
    backups = sorted((item for item in root.iterdir() if is_managed_backup(item)), reverse=True)
    for old in backups[keep:]:
        shutil.rmtree(old)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="~/.agents/skills", help="Skill install directory (Codex default: ~/.agents/skills).")
    parser.add_argument("--modules", default="all", help="all, main, main,content, or main,coding.")
    parser.add_argument("--scan-root", action="append", default=[], help="Additional skill root to scan; repeat as needed.")
    parser.add_argument("--no-default-scan-roots", action="store_true", help="Scan only the target plus explicit --scan-root paths.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print planned changes without writing.")
    args = parser.parse_args()

    target = validate_target(Path(args.target))
    modules = parse_modules(args.modules)
    scan_roots = [canonical(Path(item)) for item in args.scan_root]
    if args.dry_run:
        validate_existing_bundled_paths(target)
        custom_modules = load_existing_custom_modules(target)
        validate_existing_registry(target)
        with tempfile.TemporaryDirectory(prefix="skill-routing-dry-run-") as tmp:
            staging = Path(tmp)
            stage_packages(modules, staging)
            validate_staged_packages(modules, staging)
        print(f"Target: {target}")
        print(f"Packages: {', '.join(ROUTER_SKILLS[item] for item in modules)}")
        print(f"State: {target / '.skill-routing' / 'profile.json'}")
        if custom_modules:
            print(f"Preserved custom modules: {', '.join(item['id'] for item in custom_modules)}")
        return

    target.mkdir(parents=True, exist_ok=True)
    validate_existing_bundled_paths(target)
    custom_modules = load_existing_custom_modules(target)
    validate_existing_registry(target)
    _, _, staging_root, state_path = prepare_control_layout(target)
    with install_lock(target):
        _, _, staging_root, state_path = prepare_control_layout(target)
        staging = Path(tempfile.mkdtemp(prefix="transaction-", dir=staging_root))
        backup: Path | None = None
        state_snapshot = snapshot_state(state_path)
        state_after_init: bytes | None = None
        installed: list[Path] = []
        moved_backups: list[tuple[Path, Path]] = []
        try:
            stage_packages(modules, staging)
            validate_staged_packages(modules, staging)
            backup = create_backup_directory(target)
            installed, moved_backups = replace_packages(target, modules, staging, backup)
            registry = write_main_module_registry(target, modules, custom_modules)
            validate_installed_registry(target, registry)
            initialize_state(target, scan_roots, args.no_default_scan_roots)
            state_after_init = snapshot_state(state_path)
        except BaseException:
            rollback_packages(installed, moved_backups)
            restore_state_if_unchanged(state_path, state_snapshot, state_after_init or state_snapshot)
            cleanup_empty_backup(backup)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        cleanup_empty_backup(backup)
        prune_empty_or_old_backups(target)

    print("Installed routing skills:")
    for path in installed:
        print(f"- {path}")
    print(f"Personal profile: {target / '.skill-routing' / 'profile.json'}")
    print(f"Main registry: {registry}")
    if backup is not None and backup.exists():
        print(f"Backup: {backup}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:
        raise SystemExit(f"ERROR: {exc}") from None
