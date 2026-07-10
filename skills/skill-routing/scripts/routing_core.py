#!/usr/bin/env python3
"""Deterministic discovery, personalization, and route resolution.

The core is intentionally standard-library only.  It treats every discovered
SKILL.md as untrusted text and never imports or executes discovered resources.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
ROUTER_VERSION = "3.0"
MAX_SKILL_BYTES = 256 * 1024
MAX_DISCOVERED_SKILLS = 10_000
MAX_HISTORY = 200
PIPELINE_MIN_SCORE = 5.5
ROUTER_SKILL_NAMES = {"skill-routing", "content-skill-routing", "coding-skill-routing"}
SKIP_DIRECTORIES = {".git", ".hg", ".svn", "__pycache__", "node_modules", "vendor", ".venv", "venv"}

LATIN_TOKEN = re.compile(r"[a-z0-9]+(?:[+.#_-][a-z0-9]+)*", re.IGNORECASE)
CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
VALID_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for", "from", "in", "is", "it",
    "of", "on", "or", "the", "this", "to", "use", "user", "when", "with", "work", "needs", "need",
    "should", "wants", "want", "skill", "task", "help", "make", "please", "我", "的", "了", "和", "与", "或",
    "把", "给", "帮", "需要", "一个", "这个", "进行", "使用", "用户", "任务",
}

# A small bilingual concept bridge improves cold-start matching without a model
# or network dependency. Route packs and skill descriptions remain the primary
# source of truth; these groups only connect common cross-language phrasing.
CONCEPT_GROUPS: dict[str, tuple[str, ...]] = {
    "coding": ("code", "coding", "software", "function", "parser", "script", "代码", "编程", "函数", "脚本", "解析器"),
    "testing": ("unit test", "regression test", "test", "testing", "pytest", "jest", "单元测试", "回归测试", "测试"),
    "debugging": ("bug", "debug", "failing", "failure", "error", "broken", "regression", "修复", "报错", "失败", "调试", "回归"),
    "frontend": ("frontend", "react", "vue", "component", "layout", "responsive", "browser", "前端", "组件", "页面", "布局", "响应式", "浏览器"),
    "backend": ("backend", "api", "endpoint", "database", "postgres", "auth", "migration", "后端", "接口", "数据库", "认证", "迁移"),
    "content": ("content", "copy", "post", "newsletter", "article", "draft", "内容", "文案", "帖子", "文章", "通讯", "正文"),
    "writing": ("write", "writing", "rewrite", "edit", "prose", "tone", "clarity", "写作", "改写", "润色", "表达", "语气"),
    "humanize": ("humanize", "humanizer", "natural voice", "machine-generated", "ai writing", "less ai", "自然", "人味", "机器味", "ai味", "去掉ai", "去除ai"),
    "technical": ("technical", "technology", "terminology", "precise terms", "技术", "术语", "准确性"),
    "research": ("research", "sources", "evidence", "competitor", "latest", "调研", "研究", "来源", "证据", "竞品", "最新"),
    "visual": ("image", "visual", "cover", "card", "carousel", "thumbnail", "screenshot", "图片", "视觉", "封面", "卡片", "轮播", "缩略图", "截图"),
    "xhs": ("xiaohongshu", "rednote", "little red book", "xhs", "小红书", "红书"),
    "planning": ("plan", "architecture", "prd", "requirements", "implementation plan", "计划", "架构", "需求文档", "实施方案"),
    "review": ("review", "pull request", "pr review", "audit", "代码审查", "审查", "审核"),
    "security": ("security", "vulnerability", "threat", "安全", "漏洞", "威胁"),
    "release": ("deploy", "deployment", "release", "commit", "pull request", "部署", "发布", "提交"),
    "installation": ("install", "installer", "installation", "installing", "安装"),
    "routing": (
        "skill routing",
        "skill router",
        "route eval",
        "routing profile",
        "routing catalog",
        "route registry",
        "installed skills",
        "local skill",
        "local skills",
        "技能路由",
        "路由包",
        "本地skill",
        "已安装skill",
        "技能管理",
    ),
}

MODULE_CONCEPTS = {
    "coding": {"coding", "testing", "debugging", "frontend", "backend", "planning", "review", "security", "release", "installation", "routing"},
    "content": {"content", "writing", "humanize", "research", "visual", "xhs"},
}

CONTENT_CREATION_PHRASES = (
    "write launch post",
    "write the launch post",
    "draft launch copy",
    "draft the copy",
    "write a newsletter",
    "write an article",
    "write a post",
    "hook to this post",
    "create a social post",
    "twitter thread",
    "twitter post",
    "twitter audience",
    "announcement email",
    "launch email",
    "shareable screenshot",
    "sources for a newsletter",
    "draft an announcement",
    "写发布文案",
    "写一篇文章",
    "写帖子",
    "写一篇小红书",
    "生成文案",
    "公告邮件",
    "发布邮件",
    "分享截图",
)
SOFTWARE_WORK_PHRASES = (
    "implement",
    "build",
    "add",
    "fix",
    "debug",
    "diagnose",
    "investigate",
    "add an endpoint",
    "add a feature",
    "create a plugin",
    "create an app",
    "write unit tests",
    "write code",
    "install",
    "worker",
    "scraper",
    "webhook",
    "实现",
    "构建",
    "开发",
    "修复",
    "调试",
    "定位",
    "排查",
    "新增接口",
    "添加接口",
    "补测试",
    "写代码",
    "安装",
)
READ_ONLY_INTENT_PHRASES = (
    "only explain",
    "conceptual explanation",
    "what does",
    "what is",
    "why does",
    "research the latest",
    "compare",
    "do not modify code",
    "don't modify code",
    "no code edits",
    "no files should change",
    "without editing",
    "without modifying",
    "without changing",
    "only document",
    "只解释",
    "不要改代码",
    "不修改代码",
    "无需改代码",
    "只做调研",
    "不要修改文件",
)
MUTATION_ACTION_PHRASES = (
    "implement",
    "build",
    "fix",
    "debug",
    "add",
    "change",
    "update",
    "edit",
    "write tests",
    "create a plugin",
    "deploy",
    "实现",
    "构建",
    "修复",
    "调试",
    "新增",
    "修改",
    "更新",
    "补测试",
    "部署",
)
DIRECT_NEGATED_ACTIONS = (
    "create",
    "design",
    "generate",
    "research",
    "test",
    "review",
    "commit",
    "pull request",
    "open",
    "debug",
    "investigate",
    "deploy",
    "deployment",
    "publish",
    "write",
    "fix",
    "implement",
    "edit",
    "install",
    "创建",
    "设计",
    "生成",
    "研究",
    "调研",
    "测试",
    "审查",
    "提交",
    "拉取请求",
    "调试",
    "排查",
    "部署",
    "发布",
    "写",
    "修复",
    "实现",
    "修改",
    "安装",
)
ACTION_NEGATIONS = (
    "do not deploy",
    "don't deploy",
    "never deploy",
    "no deployment",
    "不要部署",
    "禁止部署",
    "无需部署",
    "不需要部署",
)
RELEASE_NON_DEPLOY_ACTIONS = (
    "commit",
    "pull request",
    "open pr",
    "create pr",
    "github",
    "ci",
    "提交",
    "拉取请求",
    "创建pr",
    "开pr",
)
ROUTING_MANAGEMENT_PHRASES = CONCEPT_GROUPS["routing"] + (
    "organize my skills",
    "organise my skills",
    "audit my skills",
    "refresh my skills",
    "初始化技能",
    "整理技能",
    "梳理技能",
    "审查技能",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = canonical(path)
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def default_scan_roots(cwd: Path | None = None) -> list[Path]:
    current = canonical(cwd or Path.cwd())
    project_roots: list[Path] = []
    cursor = current
    while True:
        project_roots.extend([cursor / ".agents" / "skills", cursor / ".claude" / "skills"])
        if cursor.parent == cursor or (cursor / ".git").exists():
            break
        cursor = cursor.parent
    user_roots = [
        Path("~/.agents/skills"),
        Path("~/.claude/skills"),
        Path("~/.codex/skills"),  # legacy Codex installs
        Path("~/.cc-switch/skills"),
        Path("~/AISkills"),
    ]
    return dedupe_paths([*project_roots, *user_roots])


def default_state_path(skill_root: Path) -> Path:
    configured = os.environ.get("SKILL_ROUTING_STATE")
    if configured:
        return canonical(Path(configured))
    return skill_root.parent / ".skill-routing" / "profile.json"


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(skill_file: Path) -> tuple[dict[str, str], list[str]]:
    warnings: list[str] = []
    try:
        size = skill_file.stat().st_size
    except OSError as exc:
        return {}, [f"cannot stat {skill_file}: {exc}"]
    if size > MAX_SKILL_BYTES:
        return {}, [f"frontmatter skipped: {skill_file} exceeds {MAX_SKILL_BYTES} bytes"]
    try:
        text = skill_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {}, [f"cannot read {skill_file}: {exc}"]
    if not text.startswith("---"):
        return {}, [f"missing YAML frontmatter: {skill_file}"]
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, [f"unterminated YAML frontmatter: {skill_file}"]

    metadata: dict[str, str] = {}
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1].isspace() or ":" not in line:
            index += 1
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw in {">", "|", ">-", "|-"}:
            block: list[str] = []
            index += 1
            while index < end and (not lines[index].strip() or lines[index][:1].isspace()):
                block.append(lines[index].strip())
                index += 1
            metadata[key] = (" " if raw.startswith(">") else "\n").join(part for part in block if part)
            continue
        metadata[key] = _scalar(raw)
        index += 1
    return metadata, warnings


def _is_disabled_path(path: Path) -> bool:
    return any(".disabled" in part.lower() or part.lower().endswith("-disabled") for part in path.parts)


def discover_skills(
    scan_roots: list[Path],
    max_skills: int = MAX_DISCOVERED_SKILLS,
    preferred_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    roots = dedupe_paths(scan_roots)
    preferred_paths = preferred_paths or {}
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_files: set[str] = set()

    for root_index, root in enumerate(roots):
        if not root.exists() or not root.is_dir():
            continue
        try:
            candidates = sorted(root.rglob("SKILL.md"), key=lambda item: str(item).lower())
        except OSError as exc:
            warnings.append(f"cannot scan {root}: {exc}")
            continue
        for skill_file in candidates:
            if len(records) >= max_skills:
                warnings.append(f"scan stopped after {max_skills} skills")
                break
            try:
                relative_parts = skill_file.relative_to(root).parts
            except ValueError:
                relative_parts = skill_file.parts
            if any(part in SKIP_DIRECTORIES for part in relative_parts):
                continue
            try:
                size = skill_file.stat().st_size
            except OSError as exc:
                warnings.append(f"cannot stat {skill_file}: {exc}")
                continue
            if size > MAX_SKILL_BYTES:
                warnings.append(f"frontmatter skipped: {skill_file} exceeds {MAX_SKILL_BYTES} bytes")
                continue
            resolved_file = canonical(skill_file)
            try:
                resolved_file.relative_to(root)
            except ValueError:
                warnings.append(f"skill skipped outside scan root: {skill_file} -> {resolved_file}")
                continue
            file_key = os.path.normcase(str(resolved_file))
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            metadata, parse_warnings = parse_frontmatter(skill_file)
            warnings.extend(parse_warnings)
            name = metadata.get("name", skill_file.parent.name).strip().lower()
            description = metadata.get("description", "").strip()
            when_to_use = metadata.get("when_to_use", "").strip()
            enabled = not _is_disabled_path(skill_file)
            try:
                digest = hashlib.sha256(skill_file.read_bytes()).hexdigest()
            except OSError:
                digest = ""
            record_warnings: list[str] = []
            if not VALID_SKILL_NAME.fullmatch(name):
                record_warnings.append("name does not follow the portable Agent Skills naming convention")
            if not description:
                record_warnings.append("description is empty; implicit matching will be weak")
            records.append(
                {
                    "name": name,
                    "description": description,
                    "when_to_use": when_to_use,
                    "compatibility": metadata.get("compatibility", "").strip(),
                    "path": str(canonical(skill_file.parent)),
                    "skill_file": str(resolved_file),
                    "source_root": str(root),
                    "source_rank": root_index,
                    "enabled": enabled,
                    "fingerprint": digest,
                    "warnings": record_warnings,
                }
            )
        if len(records) >= max_skills:
            break

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["name"]].append(record)

    catalog: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for name in sorted(grouped):
        variants = sorted(
            grouped[name],
            key=lambda item: (not item["enabled"], item["source_rank"], item["path"].lower()),
        )
        preferred = preferred_paths.get(name, "")
        preferred_key = os.path.normcase(str(canonical(Path(preferred)))) if preferred else ""
        preferred_variant = next(
            (item for item in variants if os.path.normcase(item["path"]) == preferred_key),
            None,
        )
        stale_preference = bool(preferred_key and preferred_variant is None)
        selected = dict(preferred_variant or variants[0])
        selected["variant_count"] = len(variants)
        selected["conflict_unresolved"] = stale_preference or (len(variants) > 1 and preferred_variant is None)
        catalog.append(selected)
        if len(variants) > 1 or stale_preference:
            conflict_paths = [item["path"] for item in variants]
            if stale_preference and preferred not in conflict_paths:
                conflict_paths.append(str(canonical(Path(preferred))))
            conflicts.append(
                {
                    "name": name,
                    "selected_path": selected["path"],
                    "paths": conflict_paths,
                    "resolved": preferred_variant is not None,
                    "reason": (
                        "user-selected path"
                        if preferred_variant is not None
                        else (
                            "preferred path is unavailable; routing is blocked until it returns or another path is selected"
                            if stale_preference
                            else "duplicate skill name; explicit path selection is required before routing"
                        )
                    ),
                }
            )

    return {
        "roots": [str(path) for path in roots],
        "catalog": catalog,
        "conflicts": conflicts,
        "warnings": warnings,
        "variants": len(records),
    }


def concepts(text: str) -> set[str]:
    found: set[str] = set()
    for concept, phrases in CONCEPT_GROUPS.items():
        if any(phrase_present(text, phrase) for phrase in phrases):
            found.add(concept)
    return found


def tokenize(text: str) -> list[str]:
    lowered = text.casefold().replace("_", " ").replace("-", " ")
    result: list[str] = []
    for token in LATIN_TOKEN.findall(lowered):
        if len(token) > 1 and token not in STOP_WORDS:
            result.append(token)
            if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
                result.append(token[:-1])
    for run in CJK_RUN.findall(lowered):
        if run not in STOP_WORDS and len(run) <= 12:
            result.append(run)
        for width in (2, 3):
            if len(run) >= width:
                result.extend(run[index : index + width] for index in range(len(run) - width + 1))
    result.extend(f"@{item}" for item in concepts(text))
    return result


def _cosine_score(query_tokens: list[str], doc_tokens: list[str], idf: dict[str, float]) -> float:
    query = Counter(query_tokens)
    document = Counter(doc_tokens)
    common = set(query) & set(document)
    if not common:
        return 0.0
    numerator = sum(query[token] * document[token] * idf.get(token, 1.0) ** 2 for token in common)
    query_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in query.items()))
    doc_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in document.items()))
    if not query_norm or not doc_norm:
        return 0.0
    return 100.0 * numerator / (query_norm * doc_norm)


def rank_catalog(prompt: str, catalog: list[dict[str, Any]], feedback: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    eligible = [
        item
        for item in catalog
        if item.get("enabled", True)
        and not item.get("conflict_unresolved", False)
        and item.get("name") not in ROUTER_SKILL_NAMES
    ]
    if not eligible:
        return []
    docs = [tokenize(f"{item['name']} {item.get('description', '')} {item.get('when_to_use', '')}") for item in eligible]
    document_frequency: Counter[str] = Counter()
    for tokens in docs:
        document_frequency.update(set(tokens))
    count = len(docs)
    idf = {token: math.log((count + 1) / (frequency + 1)) + 1.0 for token, frequency in document_frequency.items()}
    query_tokens = tokenize(prompt)
    query_lexical = {token for token in query_tokens if not token.startswith("@")}
    prompt_concepts = concepts(prompt)
    feedback = feedback or {}
    ranked: list[dict[str, Any]] = []
    for item, doc_tokens in zip(eligible, docs):
        score = _cosine_score(query_tokens, doc_tokens, idf)
        document_text = f"{item['name']} {item.get('description', '')} {item.get('when_to_use', '')}"
        shared_concepts = prompt_concepts & concepts(document_text)
        shared_lexical = query_lexical & {token for token in doc_tokens if not token.startswith("@")}
        score += 5.0 * len(shared_concepts)
        normalized_name = item["name"].replace("-", " ")
        named = phrase_present(prompt, item["name"]) or phrase_present(prompt, normalized_name)
        if named:
            score += 30.0
        action_alignment = bool(
            has_unnegated_phrase(prompt, ("install", "安装"))
            and ("installer" in item["name"] or "安装" in item["name"])
        )
        if action_alignment:
            score += 25.0
        # Feedback can reorder relevant candidates, but it must never manufacture
        # relevance for a prompt with no metadata or concept overlap.
        if score > 0:
            stats = feedback.get(item["name"], {})
            score += min(20.0, max(-20.0, 8.0 * (stats.get("success", 0) - stats.get("failure", 0))))
        if score > 0:
            ranked.append(
                {
                    "name": item["name"],
                    "path": item["path"],
                    "score": round(score, 3),
                    "description": item.get("description", ""),
                    "reason": "local metadata match",
                    "evidence": {
                        "named": named,
                        "action_alignment": action_alignment,
                        "lexical_matches": sorted(shared_lexical),
                        "concept_matches": sorted(shared_concepts),
                    },
                }
            )
    ranked.sort(key=lambda item: (-item["score"], item["name"], item["path"]))
    return ranked


def resolve_module_path(skill_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return canonical(path if path.is_absolute() else skill_root / path)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def validate_module_registry_data(data: Any, source: str) -> list[str]:
    if not isinstance(data, dict):
        return [f"{source}: module registry must contain a JSON object"]
    errors: list[str] = []
    if not isinstance(data.get("version"), int) or data.get("version", 0) < 2:
        errors.append(f"{source}: module registry version must be an integer >= 2")
    modules = data.get("modules")
    if not isinstance(modules, list):
        errors.append(f"{source}: modules must be a list")
        return errors
    seen: set[str] = set()
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            errors.append(f"{source}: modules[{index}] must be an object")
            continue
        module_id = module.get("id")
        if not isinstance(module_id, str) or not module_id:
            errors.append(f"{source}: modules[{index}].id must be a non-empty string")
            continue
        if module_id in seen:
            errors.append(f"{source}: duplicate module id: {module_id}")
        seen.add(module_id)
        if "enabled" in module and not isinstance(module.get("enabled"), bool):
            errors.append(f"{source}: modules[{index}].enabled must be a boolean")
        if "label" in module and not isinstance(module.get("label"), str):
            errors.append(f"{source}: modules[{index}].label must be a string")
        for field in ("skill_path", "registry_path"):
            if not isinstance(module.get(field), str) or not module.get(field):
                errors.append(f"{source}: modules[{index}].{field} must be a non-empty string")
        _, domain_errors = string_list_errors(module.get("domains", []), f"{source}: modules[{index}].domains")
        errors.extend(domain_errors)
    return errors


@contextmanager
def state_lock(state_path: Path, stale_after: int = 120, wait_timeout: float = 10.0) -> Iterator[None]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    deadline = time.monotonic() + wait_timeout
    token = secrets.token_hex(16)
    owner_text = f"pid={os.getpid()}\ntoken={token}\n"

    def owner_is_running() -> bool:
        try:
            content = lock_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"^pid=(\d+)$", content, re.MULTILINE)
            if not match:
                return False
            pid = int(match.group(1))
            if os.name == "nt":
                # Python maps os.kill(pid, 0) to TerminateProcess on Windows.
                # Fail closed rather than killing a live state-lock owner.
                return True
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (FileNotFoundError, OSError, ValueError):
            return False

    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0
            if age > stale_after and not owner_is_running():
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for routing state update: {lock_path}")
            time.sleep(0.05)
            continue
        try:
            os.write(descriptor, owner_text.encode())
        except Exception:
            os.close(descriptor)
            lock_path.unlink(missing_ok=True)
            raise
        os.close(descriptor)
        break
    try:
        yield
    finally:
        try:
            current = lock_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            current = ""
        if f"token={token}" in current:
            lock_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def load_modules(skill_root: Path, modules_path: Path) -> list[dict[str, Any]]:
    data = load_json(modules_path, {"modules": []})
    module_errors = validate_module_registry_data(data, str(modules_path))
    if module_errors:
        raise ValueError("; ".join(module_errors))
    modules: list[dict[str, Any]] = []
    for raw in data.get("modules", []):
        if not raw.get("enabled", True):
            continue
        module = dict(raw)
        module["skill_path_resolved"] = str(resolve_module_path(skill_root, raw.get("skill_path", "")))
        module["registry_path_resolved"] = str(resolve_module_path(skill_root, raw.get("registry_path", "")))
        registry = load_json(Path(module["registry_path_resolved"]), None)
        if registry is None:
            raise ValueError(f"{raw.get('id')}: missing registry {module['registry_path_resolved']}")
        errors = validate_registry(registry, str(module["registry_path_resolved"]))
        if errors:
            raise ValueError("; ".join(errors))
        module["registry"] = registry
        modules.append(module)
    return modules


def _stage_query(module: dict[str, Any], stage: dict[str, Any]) -> str:
    registry = module["registry"]
    related = [
        skill
        for skill in registry.get("skills", [])
        if stage.get("id") in skill.get("stages", [])
    ]
    parts = [
        module.get("label", ""),
        " ".join(module.get("domains", [])),
        stage.get("id", ""),
        stage.get("purpose", ""),
        stage.get("layer", ""),
    ]
    for skill in related:
        parts.extend([skill.get("name", ""), skill.get("category", ""), skill.get("use_when", "")])
    return " ".join(parts)


def build_bindings(modules: list[dict[str, Any]], catalog: list[dict[str, Any]], old: dict[str, Any]) -> dict[str, Any]:
    bindings: dict[str, Any] = {}
    old_bindings = old.get("bindings", {}) if old else {}
    for module in modules:
        module_id = module["id"]
        for stage in module["registry"].get("stages", []):
            key = f"{module_id}:{stage['id']}"
            # Preserve explicit choices even while a skill is temporarily moved
            # or uninstalled; resolution ignores it until the skill returns.
            manual = list(dict.fromkeys(old_bindings.get(key, {}).get("manual", [])))
            ranked = rank_catalog(_stage_query(module, stage), catalog)
            automatic = [
                {"name": item["name"], "score": item["score"]}
                for item in ranked
                if item["score"] >= 22.0
            ][:5]
            bindings[key] = {"manual": manual, "automatic": automatic}
    return bindings


def initialize_profile(
    skill_root: Path,
    modules_path: Path,
    state_path: Path,
    scan_roots: list[Path],
) -> tuple[dict[str, Any], dict[str, Any]]:
    with state_lock(state_path):
        old = load_json(state_path, {}) or {}
        if old:
            errors = profile_validation_errors(old, str(state_path))
            if errors:
                raise ValueError("; ".join(errors))
        preferences = old.get("preferences", {"disabled_skills": [], "preferred_paths": {}})
        preferences.setdefault("disabled_skills", [])
        preferences.setdefault("preferred_paths", {})
        discovered = discover_skills(scan_roots, preferred_paths=preferences["preferred_paths"])
        modules = load_modules(skill_root, modules_path)
        profile = {
            "schema_version": SCHEMA_VERSION,
            "router_version": ROUTER_VERSION,
            "created_at": old.get("created_at", utc_now()),
            "updated_at": utc_now(),
            "scan_roots": discovered["roots"],
            "catalog": discovered["catalog"],
            "conflicts": discovered["conflicts"],
            "scan_warnings": discovered["warnings"],
            "bindings": {},
            "resolutions": old.get("resolutions", {}),
            "preferences": preferences,
            "feedback": old.get("feedback", {}),
            "history": old.get("history", [])[-MAX_HISTORY:],
        }
        profile["bindings"] = build_bindings(modules, profile["catalog"], old)
        atomic_write_json(state_path, profile)
    summary = {
        "initialized": True,
        "state_path": str(state_path),
        "inventory": {
            "effective_skills": len(profile["catalog"]),
            "variants": discovered["variants"],
            "conflicts": len(profile["conflicts"]),
            "warnings": len(profile["scan_warnings"]),
        },
        "route_packs": [module["id"] for module in modules],
        "bindings": {
            "stages": len(profile["bindings"]),
            "automatic_candidates": sum(len(value.get("automatic", [])) for value in profile["bindings"].values()),
            "manual_candidates": sum(len(value.get("manual", [])) for value in profile["bindings"].values()),
        },
    }
    return profile, summary


def empty_profile() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "router_version": ROUTER_VERSION,
        "scan_roots": [],
        "catalog": [],
        "conflicts": [],
        "scan_warnings": [],
        "bindings": {},
        "resolutions": {},
        "preferences": {"disabled_skills": [], "preferred_paths": {}},
        "feedback": {},
        "history": [],
    }


def profile_validation_errors(profile: Any, source: str = "profile") -> list[str]:
    if not isinstance(profile, dict):
        return [f"{source}: profile must contain a JSON object"]
    errors: list[str] = []
    if profile.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{source}: unsupported schema {profile.get('schema_version')!r}")
        return errors
    if not isinstance(profile.get("router_version"), str):
        errors.append(f"{source}: router_version must be a string")
    _, scan_root_errors = string_list_errors(profile.get("scan_roots"), f"{source}: scan_roots")
    errors.extend(scan_root_errors)
    for field in ("catalog", "conflicts", "history"):
        if not isinstance(profile.get(field, []), list):
            errors.append(f"{source}: {field} must be a list")
    for field in ("bindings", "resolutions", "preferences", "feedback"):
        if not isinstance(profile.get(field, {}), dict):
            errors.append(f"{source}: {field} must be an object")
    if errors:
        return errors
    for index, item in enumerate(profile.get("catalog", [])):
        if not isinstance(item, dict):
            errors.append(f"{source}: catalog[{index}] must be an object")
            continue
        for field in ("name", "description", "path", "skill_file", "source_root", "fingerprint"):
            if not isinstance(item.get(field), str):
                errors.append(f"{source}: catalog[{index}].{field} must be a string")
        if "enabled" in item and not isinstance(item.get("enabled"), bool):
            errors.append(f"{source}: catalog[{index}].enabled must be a boolean")
        if "conflict_unresolved" in item and not isinstance(item.get("conflict_unresolved"), bool):
            errors.append(f"{source}: catalog[{index}].conflict_unresolved must be a boolean")
    for index, item in enumerate(profile.get("conflicts", [])):
        if not isinstance(item, dict):
            errors.append(f"{source}: conflicts[{index}] must be an object")
            continue
        if not isinstance(item.get("name"), str):
            errors.append(f"{source}: conflicts[{index}].name must be a string")
        if not isinstance(item.get("selected_path"), str):
            errors.append(f"{source}: conflicts[{index}].selected_path must be a string")
        if not isinstance(item.get("resolved"), bool):
            errors.append(f"{source}: conflicts[{index}].resolved must be a boolean")
        if not isinstance(item.get("reason"), str):
            errors.append(f"{source}: conflicts[{index}].reason must be a string")
        paths, path_errors = string_list_errors(item.get("paths"), f"{source}: conflicts[{index}].paths", required=True)
        errors.extend(path_errors)
        if len(paths) < 2:
            errors.append(f"{source}: conflicts[{index}].paths must contain at least two paths")
    preferences = profile.get("preferences", {})
    disabled, disabled_errors = string_list_errors(preferences.get("disabled_skills", []), f"{source}: preferences.disabled_skills")
    errors.extend(disabled_errors)
    preferred_paths = preferences.get("preferred_paths", {})
    if not isinstance(preferred_paths, dict):
        errors.append(f"{source}: preferences.preferred_paths must be an object")
    else:
        for key, value in preferred_paths.items():
            if not isinstance(key, str) or not isinstance(value, str):
                errors.append(f"{source}: preferences.preferred_paths must map strings to strings")
                break
    for key, value in profile.get("bindings", {}).items():
        if not isinstance(key, str) or not isinstance(value, dict):
            errors.append(f"{source}: bindings must map strings to objects")
            continue
        _, manual_errors = string_list_errors(value.get("manual", []), f"{source}: bindings[{key}].manual")
        errors.extend(manual_errors)
        automatic = value.get("automatic", [])
        if not isinstance(automatic, list) or not all(isinstance(item, dict) for item in automatic):
            errors.append(f"{source}: bindings[{key}].automatic must be a list of objects")
            continue
        for index, item in enumerate(automatic):
            if not isinstance(item.get("name"), str):
                errors.append(f"{source}: bindings[{key}].automatic[{index}].name must be a string")
            if not isinstance(item.get("score"), (int, float)):
                errors.append(f"{source}: bindings[{key}].automatic[{index}].score must be a number")
    for key, value in profile.get("resolutions", {}).items():
        if not isinstance(key, str) or not isinstance(value, dict):
            errors.append(f"{source}: resolutions must map strings to objects")
            continue
        if value.get("action") not in {"replace", "fallback", "disable"}:
            errors.append(f"{source}: resolutions[{key}].action must be replace, fallback, or disable")
        if value.get("replacement") is not None and not isinstance(value.get("replacement"), str):
            errors.append(f"{source}: resolutions[{key}].replacement must be a string or null")
    for key, value in profile.get("feedback", {}).items():
        if not isinstance(key, str) or not isinstance(value, dict):
            errors.append(f"{source}: feedback must map strings to objects")
            continue
        for outcome in ("success", "failure"):
            if not isinstance(value.get(outcome, 0), int) or int(value.get(outcome, 0)) < 0:
                errors.append(f"{source}: feedback[{key}].{outcome} must be a non-negative integer")
    return errors


def read_profile(state_path: Path) -> dict[str, Any]:
    profile = load_json(state_path, None)
    if profile is None:
        return empty_profile()
    errors = profile_validation_errors(profile, str(state_path))
    if errors:
        raise ValueError("; ".join(errors))
    return profile


def phrase_present(text: str, phrase: str) -> bool:
    lowered = text.casefold().replace("’", "'")
    needle = phrase.casefold().replace("’", "'").strip()
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9 _+.#-]+", needle):
        pattern = r"(?<![a-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
        return re.search(pattern, lowered) is not None
    return needle in lowered


def phrase_negated(text: str, phrase: str) -> bool:
    lowered = text.casefold().replace("’", "'")
    needle = phrase.casefold().replace("’", "'").strip()
    if not needle:
        return False
    if re.fullmatch(r"[a-z0-9 _+.#-]+", needle):
        pattern = r"(?<![a-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
        indices = [match.start() for match in re.finditer(pattern, lowered)]
    else:
        indices = []
        start = 0
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            indices.append(index)
            start = index + max(1, len(needle))
    if not indices:
        return False

    def occurrence_negated(index: int) -> bool:
        prefix = lowered[max(0, index - 32) : index]
        # Negation is clause-local. Otherwise “不要写帖子，只实现接口”
        # incorrectly negates the later implementation clause.
        prefix = re.split(r"[,;:，；：。！？!?]|\bbut\b|\brather\b|\binstead\b|但是|不过|而是|但", prefix)[-1]
        return any(
            marker in prefix
            for marker in (
                "do not ",
                "don't ",
                "not ",
                "no ",
                "never ",
                "without ",
                "不要",
                "禁止",
                "无需",
                "不需要",
                "不是",
                "不写",
                "别",
            )
        )

    return all(occurrence_negated(index) for index in indices)


def has_unnegated_phrase(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase_present(text, phrase) and not phrase_negated(text, phrase) for phrase in phrases)


def has_read_only_intent(prompt: str) -> bool:
    return has_unnegated_phrase(prompt, READ_ONLY_INTENT_PHRASES) and not has_unnegated_phrase(
        prompt, MUTATION_ACTION_PHRASES
    )


def _simple_similarity(left: str, right: str) -> float:
    left_tokens = Counter(tokenize(left))
    right_tokens = Counter(tokenize(right))
    common = set(left_tokens) & set(right_tokens)
    if not common:
        return 0.0
    numerator = sum(min(left_tokens[token], right_tokens[token]) for token in common)
    denominator = math.sqrt(sum(left_tokens.values()) * sum(right_tokens.values()))
    return 100.0 * numerator / denominator if denominator else 0.0


def score_pipeline(module: dict[str, Any], pipeline: dict[str, Any], prompt: str) -> tuple[float, list[str]]:
    if module.get("id") == "coding" and pipeline.get("domain") not in {"review", "release"} and has_read_only_intent(prompt):
        return 0.0, ["read-only intent excludes an implementation pipeline"]
    if pipeline.get("domain") == "release" and any(phrase_present(prompt, phrase) for phrase in ACTION_NEGATIONS):
        deploy_requested = has_unnegated_phrase(prompt, ("deploy", "deployment", "ship live", "go live", "部署", "上线"))
        other_action = any(
            phrase_present(prompt, phrase) and not phrase_negated(prompt, phrase)
            for phrase in RELEASE_NON_DEPLOY_ACTIONS
        )
        if not deploy_requested and not other_action:
            return 0.0, ["deployment is negated and no other release action is requested"]
    required_any = pipeline.get("required_any", [])
    if required_any and not any(
        phrase_present(prompt, phrase) and not phrase_negated(prompt, phrase)
        for phrase in required_any
    ):
        return 0.0, []
    intent_any = pipeline.get("intent_any", [])
    if intent_any and not has_unnegated_phrase(prompt, intent_any):
        return 0.0, []
    excluded = [
        phrase
        for phrase in pipeline.get("exclude", [])
        if phrase_present(prompt, phrase) and not phrase_negated(prompt, phrase)
    ]
    if excluded:
        return 0.0, [f"excluded by {phrase}" for phrase in excluded]

    reasons: list[str] = []
    score = 0.0
    for trigger in pipeline.get("triggers", []):
        if phrase_present(prompt, trigger) and not phrase_negated(prompt, trigger):
            weight = 7.0 if " " in trigger or len(trigger) >= 5 else 5.0
            score += weight
            reasons.append(f"trigger:{trigger}")
    searchable = " ".join(
        [
            pipeline.get("label", ""),
            pipeline.get("domain", ""),
            " ".join(pipeline.get("triggers", [])),
        ]
    )
    score += min(12.0, _simple_similarity(prompt, searchable) * 0.18)
    prompt_concepts = concepts(prompt)
    module_hits = prompt_concepts & MODULE_CONCEPTS.get(module["id"], set())
    score += 3.0 * len(module_hits)
    if module_hits:
        reasons.append("concepts:" + ",".join(sorted(module_hits)))
    return score, reasons


def pipeline_candidates(modules: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for module in modules:
        for pipeline in module["registry"].get("pipelines", []):
            score, reasons = score_pipeline(module, pipeline, prompt)
            if score > 0:
                scored.append({"module": module, "pipeline": pipeline, "score": round(score, 3), "reasons": reasons})
    scored.sort(key=lambda item: (-item["score"], item["module"]["id"], item["pipeline"]["id"]))
    return scored


def _registered_skill_modules(modules: list[dict[str, Any]]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = defaultdict(set)
    for module in modules:
        for skill in module["registry"].get("skills", []):
            mapping[skill["name"]].add(module["id"])
    return mapping


def _installed_map(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    disabled = set(profile.get("preferences", {}).get("disabled_skills", []))
    return {
        item["name"]: item
        for item in profile.get("catalog", [])
        if item.get("enabled", True)
        and not item.get("conflict_unresolved", False)
        and item["name"] not in disabled
    }


def is_routing_management_request(prompt: str) -> bool:
    stripped = prompt.casefold().strip()
    if stripped in {"init", "initialize", "refresh", "inventory", "doctor", "validate", "初始化", "刷新", "诊断"}:
        return True
    strong_management_phrases = (
        "skill routing",
        "skill router",
        "routing profile",
        "routing catalog",
        "route registry",
        "route pack",
        "local skills",
        "installed skills",
        "技能路由",
        "路由包",
        "本地skill",
        "已安装skill",
    )
    management_action_phrases = (
        "init",
        "initialize",
        "refresh",
        "rescan",
        "scan",
        "inventory",
        "list",
        "audit",
        "organize",
        "organise",
        "validate",
        "doctor",
        "check duplicate",
        "duplicate names",
        "stale local skill bindings",
        "初始化",
        "刷新",
        "重新扫描",
        "扫描",
        "列出",
        "整理",
        "梳理",
        "校验",
        "检查重复",
        "重复名称",
    )
    has_strong_management = any(phrase_present(prompt, phrase) for phrase in strong_management_phrases)
    has_management_action = any(phrase_present(prompt, phrase) for phrase in management_action_phrases)
    if has_strong_management and (has_management_action or not has_unnegated_phrase(prompt, SOFTWARE_WORK_PHRASES)):
        return True
    if has_unnegated_phrase(prompt, SOFTWARE_WORK_PHRASES):
        return False
    return any(phrase_present(prompt, phrase) for phrase in ROUTING_MANAGEMENT_PHRASES)


def direct_candidate_is_negated(prompt: str, candidate: dict[str, Any]) -> bool:
    name = candidate.get("name", "").casefold()
    name_phrases = (name, name.replace("-", " "))
    if any(phrase_present(prompt, phrase) and phrase_negated(prompt, phrase) for phrase in name_phrases if phrase):
        return True
    name_markers = {
        "deploy": ("deploy",),
        "deployment": ("deploy",),
        "publish": ("publish", "publisher"),
        "create": ("creator", "builder"),
        "design": ("design", "designer", "canvas"),
        "generate": ("gen", "generator", "imagegen"),
        "research": ("research", "search", "anysearch"),
        "test": ("test", "testing", "playwright", "browser"),
        "review": ("review",),
        "commit": ("commit", "git-commit"),
        "pull request": ("pr-creation", "pull-request", "github-pr"),
        "open": ("pr-creation", "pull-request", "github-pr"),
        "debug": ("debug", "debugging"),
        "investigate": ("debug", "debugging"),
        "write": ("writer", "writing"),
        "fix": ("fix",),
        "implement": ("implementation", "implementer"),
        "edit": ("editor", "editing"),
        "install": ("installer",),
        "创建": ("创建", "creator"),
        "设计": ("设计", "design", "designer", "canvas"),
        "生成": ("生成", "gen", "generator", "imagegen"),
        "研究": ("研究", "research", "search", "anysearch"),
        "调研": ("调研", "research", "search", "anysearch"),
        "测试": ("测试", "test", "playwright"),
        "审查": ("审查", "review"),
        "提交": ("提交", "commit", "git-commit"),
        "拉取请求": ("pr-creation", "pull-request", "github-pr"),
        "调试": ("调试", "debug", "debugging"),
        "排查": ("排查", "debug", "debugging"),
        "部署": ("部署",),
        "发布": ("发布",),
        "写": ("写作", "writer"),
        "修复": ("修复",),
        "实现": ("实现",),
        "修改": ("修改", "editor"),
        "安装": ("安装", "installer"),
    }
    return any(
        phrase_negated(prompt, action)
        and any(marker in name for marker in name_markers.get(action, (action,)))
        for action in DIRECT_NEGATED_ACTIONS
    )


def candidate_evidence_is_specific(candidate: dict[str, Any]) -> bool:
    evidence = candidate.get("evidence", {})
    return bool(evidence.get("named") or evidence.get("action_alignment")) or (
        len(evidence.get("lexical_matches", [])) >= 2
        or len(evidence.get("concept_matches", [])) >= 2
    )


def _resolution_key(module_id: str, stage: str, skill: str) -> str:
    return f"{module_id}:{stage}:{skill}"


def _decision_actions(module_id: str, stage: str, missing: str, install_hint: str = "") -> list[dict[str, Any]]:
    return [
        {
            "action": "install",
            "requires_confirmation": True,
            "skill": missing,
            "install_hint": install_hint,
            "instruction": "Ask the user to approve a trusted installer and source; never execute install_hint as a shell command.",
        },
        {
            "action": "replace",
            "requires_confirmation": False,
            "instruction": "Choose an installed equivalent and persist it with the resolve command.",
        },
        {
            "action": "fallback",
            "requires_confirmation": False,
            "instruction": "Use the host agent's general capability for this stage and remember the decision.",
        },
        {
            "action": "disable",
            "requires_confirmation": False,
            "instruction": "Remove this route node from future plans in the selected profile scope.",
        },
    ]


def _registry_skill_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in registry.get("skills", [])}


def resolve_stage(
    module_id: str,
    registry: dict[str, Any],
    stage_entry: dict[str, Any],
    profile: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    stage = stage_entry["stage"]
    conditions = stage_entry.get("candidate_conditions", {})
    all_declared = list(stage_entry.get("candidate_skills", []))
    declared = [
        name
        for name in all_declared
        if not conditions.get(name)
        or any(phrase_present(prompt, phrase) and not phrase_negated(prompt, phrase) for phrase in conditions[name])
    ]
    conditionally_excluded = set(all_declared) - set(declared)
    if not declared:
        return {"status": "router_handled", "selected": [], "missing": [], "actions": []}

    installed = _installed_map(profile)
    resolutions = profile.get("resolutions", {})
    registry_skills = _registry_skill_map(registry)
    binding = profile.get("bindings", {}).get(f"{module_id}:{stage}", {})
    for name in binding.get("manual", []):
        if name in installed and name not in conditionally_excluded:
            return {
                "status": "selected",
                "selected": [{"name": name, "path": installed[name]["path"], "score": 20_000, "reason": "manual binding"}],
                "missing": [],
                "actions": [],
            }
    chosen: list[dict[str, Any]] = []
    missing: list[str] = []
    disabled_candidates: list[str] = []
    fallback_requested = False

    for position, name in enumerate(declared):
        decision = resolutions.get(_resolution_key(module_id, stage, name), {})
        action = decision.get("action")
        if action == "replace":
            replacement = decision.get("replacement")
            if replacement in installed:
                chosen.append(
                    {
                        "name": replacement,
                        "path": installed[replacement]["path"],
                        "score": 10_000 - position,
                        "reason": "user replacement",
                        "replaces": name,
                    }
                )
                continue
        if action == "fallback":
            fallback_requested = True
            missing.append(name)
            continue
        if action == "disable":
            disabled_candidates.append(name)
            continue
        if name in installed:
            direct = next((item for item in rank_catalog(prompt, [installed[name]], profile.get("feedback")) if item["name"] == name), None)
            chosen.append(
                {
                    "name": name,
                    "path": installed[name]["path"],
                    "score": round(1_000 - position * 10 + (direct or {}).get("score", 0), 3),
                    "reason": "installed route-pack candidate",
                }
            )
        else:
            missing.append(name)

    if chosen:
        chosen.sort(key=lambda item: (-item["score"], item["name"]))
        limit = max(1, int(stage_entry.get("max_skills", 1)))
        return {
            "status": "selected",
            "selected": chosen[:limit],
            "missing": [],
            "unavailable_alternatives": missing,
            "disabled_candidates": disabled_candidates,
            "actions": [],
        }

    if fallback_requested:
        return {
            "status": "agent_fallback",
            "selected": [],
            "missing": missing,
            "actions": [],
            "degraded": True,
            "reason": "user declined installation and chose the host agent fallback",
        }

    if missing:
        declared_set = set(declared)
        registry_names = set(registry_skills)
        for item in binding.get("automatic", []):
            name = item["name"]
            if name in installed and name not in registry_names and name not in declared_set and name not in conditionally_excluded:
                prompt_match = next(
                    iter(rank_catalog(prompt, [installed[name]], profile.get("feedback"))),
                    None,
                )
                if prompt_match is None or not candidate_evidence_is_specific(prompt_match):
                    continue
                return {
                    "status": "selected",
                    "selected": [
                        {
                            "name": name,
                            "path": installed[name]["path"],
                            "score": round(500 + prompt_match["score"], 3),
                            "reason": "automatic capability fallback",
                        }
                    ],
                    "missing": [],
                    "unavailable_alternatives": missing,
                    "actions": [],
                    "degraded": True,
                }

        primary_missing = missing[0]
        install_hint = registry_skills.get(primary_missing, {}).get("install_hint", "")
        return {
            "status": "decision_required",
            "selected": [],
            "missing": missing,
            "disabled_candidates": disabled_candidates,
            "actions": _decision_actions(module_id, stage, primary_missing, install_hint),
            "reason": "no installed compatible candidate or remembered fallback",
        }

    if disabled_candidates:
        return {
            "status": "disabled",
            "selected": [],
            "missing": [],
            "disabled_candidates": disabled_candidates,
            "actions": [],
            "degraded": True,
            "reason": "all compatible candidates were disabled by the user",
        }

    return {"status": "router_handled", "selected": [], "missing": [], "actions": []}


def grouped_stages(pipeline: dict[str, Any]) -> list[tuple[int, list[dict[str, Any]]]]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, stage in enumerate(pipeline.get("stages", []), start=1):
        groups[int(stage.get("step", index))].append(stage)
    return [(step, groups[step]) for step in sorted(groups)]


def build_domain_plan(candidate: dict[str, Any], profile: dict[str, Any], prompt: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    module = candidate["module"]
    pipeline = candidate["pipeline"]
    registry = module["registry"]
    stage_meta = {item["id"]: item for item in registry.get("stages", [])}
    steps: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    decisions = 0
    for step, entries in grouped_stages(pipeline):
        stage_results: list[dict[str, Any]] = []
        for entry in entries:
            resolution = resolve_stage(module["id"], registry, entry, profile, prompt)
            if resolution["status"] == "decision_required":
                decisions += 1
            selected.extend(resolution.get("selected", []))
            meta = stage_meta.get(entry["stage"], {})
            stage_results.append(
                {
                    "stage": entry["stage"],
                    "layer": meta.get("layer"),
                    "purpose": meta.get("purpose"),
                    "execution": entry.get("execution", "serial"),
                    "parallel_group": entry.get("parallel_group"),
                    "depends_on": entry.get("depends_on", []),
                    "agent_role": entry.get("agent_role"),
                    "declared_candidates": entry.get("candidate_skills", []),
                    "resolution": resolution,
                }
            )
        steps.append(
            {
                "step": step,
                "parallel": len(entries) > 1 or any(item.get("execution") == "parallel" for item in entries),
                "stages": stage_results,
            }
        )
    domain_plan = {
        "router": registry.get("router"),
        "matched": True,
        "recommended_pipeline": pipeline["id"],
        "label": pipeline.get("label", ""),
        "domain": pipeline.get("domain"),
        "mode": pipeline.get("mode", "default"),
        "score": candidate["score"],
        "match_reasons": candidate["reasons"],
        "steps": steps,
        "decision_required_count": decisions,
        "process_report_template": "stage -> selected skill or fallback -> evidence/gate -> status",
    }
    return domain_plan, selected


def _unique_skills(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if item["name"] not in seen:
            seen.add(item["name"])
            result.append(item)
    return result


def route_prompt(skill_root: Path, modules_path: Path, state_path: Path, prompt: str, top_k: int = 3) -> dict[str, Any]:
    profile = read_profile(state_path)
    modules = load_modules(skill_root, modules_path)
    skill_modules = _registered_skill_modules(modules)
    explicit_content_deliverable = has_unnegated_phrase(prompt, CONTENT_CREATION_PHRASES)
    explicit_software_work = has_unnegated_phrase(prompt, SOFTWARE_WORK_PHRASES)
    direct = [
        item
        for item in rank_catalog(prompt, profile.get("catalog", []), profile.get("feedback", {}))
        if not direct_candidate_is_negated(prompt, item)
    ]
    if explicit_software_work and not explicit_content_deliverable:
        direct = [
            item
            for item in direct
            if skill_modules.get(item["name"], set()) != {"content"}
        ]
    direct = direct[: max(1, top_k)]
    pipelines = pipeline_candidates(modules, prompt)

    # Explicit router-management requests belong to the control plane.
    if is_routing_management_request(prompt):
        return {
            "prompt": prompt,
            "matched": True,
            "route_kind": "management",
            "recommended_module": None,
            "confidence": 1.0,
            "selected_skills": [],
            "message": "Keep this request in skill-routing; use init, inventory, bind, resolve, feedback, doctor, or validate.",
            "initialized": bool(profile.get("catalog") or state_path.exists()),
        }

    best_pipeline = pipelines[0] if pipelines else None
    best_pipeline_score = best_pipeline["score"] if best_pipeline else 0.0
    best_direct_score = direct[0]["score"] if direct else 0.0

    # Compose clearly independent content-creation and software clauses.  A
    # shared noun such as "newsletter parser" is not enough; the request must
    # contain a separate content deliverable and a software intent.
    if explicit_content_deliverable and explicit_software_work:
        best_by_module: dict[str, dict[str, Any]] = {}
        for item in pipelines:
            best_by_module.setdefault(item["module"]["id"], item)
        if {"coding", "content"}.issubset(best_by_module) and all(
            best_by_module[key]["score"] >= PIPELINE_MIN_SCORE for key in ("coding", "content")
        ):
            ordered = [best_by_module["coding"], best_by_module["content"]]
            plans: dict[str, Any] = {}
            selected: list[dict[str, Any]] = []
            for item in ordered:
                domain_plan, domain_selected = build_domain_plan(item, profile, prompt)
                plans[item["module"]["id"]] = domain_plan
                selected.extend(domain_selected)
            return {
                "prompt": prompt,
                "matched": True,
                "route_kind": "composed_pipeline",
                "recommended_module": None,
                "recommended_modules": ["coding", "content"],
                "confidence": round(min(1.0, min(item["score"] for item in ordered) / 25.0), 3),
                "selected_skills": _unique_skills(selected),
                "domain_plans": plans,
                "domain_plan": plans["coding"],
                "initialized": bool(profile.get("catalog") or state_path.exists()),
                "decision_trace": {
                    "reason": "the request contains separate software and content deliverables",
                    "module_scores": {item["module"]["id"]: item["score"] for item in ordered},
                },
            }

    # Direct routing is deliberately conservative in large catalogs. A modest
    # metadata overlap is an alternative to inspect, not enough to activate a
    # skill. Strong multi-stage deliverables keep their route-pack plan unless
    # the user explicitly named a skill or the local match is exceptionally
    # strong and clearly separated from the runner-up.
    direct_runner_up = direct[1]["score"] if len(direct) > 1 else 0.0
    direct_margin = best_direct_score - direct_runner_up
    explicit_skill = bool(direct) and (
        phrase_present(prompt, direct[0]["name"])
        or phrase_present(prompt, direct[0]["name"].replace("-", " "))
    )
    evidence_confident = bool(direct) and candidate_evidence_is_specific(direct[0])
    direct_confident = evidence_confident and best_direct_score >= 18.0 and (
        direct_margin >= 4.0 or best_direct_score >= 55.0 or explicit_skill
    )
    use_direct = direct_confident and (
        best_pipeline_score < 10.0
        or explicit_skill
        or (best_direct_score >= 55.0 and best_direct_score >= best_pipeline_score * 2.2)
    )
    if best_pipeline is not None and best_pipeline_score >= PIPELINE_MIN_SCORE and direct:
        best_pipeline_skills = {
            skill
            for entry in best_pipeline["pipeline"].get("stages", [])
            for skill in entry.get("candidate_skills", [])
        }
        if direct[0]["name"] in best_pipeline_skills or best_pipeline["pipeline"].get("domain") == "release":
            use_direct = False
    if use_direct:
        selected = direct[:1]
        modules_for_skill = sorted(skill_modules.get(selected[0]["name"], []))
        confidence = min(1.0, selected[0]["score"] / 65.0)
        return {
            "prompt": prompt,
            "matched": True,
            "route_kind": "direct",
            "recommended_module": modules_for_skill[0] if len(modules_for_skill) == 1 else None,
            "confidence": round(confidence, 3),
            "selected_skills": selected,
            "alternatives": direct[1:top_k],
            "initialized": bool(profile.get("catalog") or state_path.exists()),
            "decision_trace": {
                "direct_score": best_direct_score,
                "direct_margin": round(direct_margin, 3),
                "best_pipeline_score": best_pipeline_score,
                "reason": "a local skill is a stronger fit than the available pipeline templates",
            },
        }

    if best_pipeline is None or best_pipeline_score < PIPELINE_MIN_SCORE:
        return {
            "prompt": prompt,
            "matched": False,
            "route_kind": "abstain",
            "recommended_module": None,
            "confidence": 0.0,
            "selected_skills": [],
            "alternatives": direct,
            "initialized": bool(profile.get("catalog") or state_path.exists()),
            "message": "No route met the confidence threshold. Clarify the deliverable or bind a local skill.",
        }

    domain_plan, selected = build_domain_plan(best_pipeline, profile, prompt)
    margin = best_pipeline_score - (pipelines[1]["score"] if len(pipelines) > 1 else 0.0)
    confidence = min(1.0, (best_pipeline_score / 35.0) * (0.7 + min(0.3, max(0.0, margin) / 20.0)))
    return {
        "prompt": prompt,
        "matched": True,
        "route_kind": "pipeline",
        "recommended_module": best_pipeline["module"]["id"],
        "recommended_modules": [best_pipeline["module"]["id"]],
        "confidence": round(confidence, 3),
        "selected_skills": _unique_skills(selected),
        "domain_plan": domain_plan,
        "alternatives": [
            {"module": item["module"]["id"], "pipeline": item["pipeline"]["id"], "score": item["score"]}
            for item in pipelines[1:top_k]
        ],
        "initialized": bool(profile.get("catalog") or state_path.exists()),
        "decision_trace": {
            "pipeline_score": best_pipeline_score,
            "runner_up_margin": round(margin, 3),
            "direct_score": best_direct_score,
        },
    }


def update_profile(state_path: Path, mutate: Any) -> Any:
    """Apply one read-modify-write transaction while holding the state lock."""
    with state_lock(state_path):
        profile = read_profile(state_path)
        result = mutate(profile)
        profile["updated_at"] = utc_now()
        atomic_write_json(state_path, profile)
    return result


def bind_skill(state_path: Path, modules: list[dict[str, Any]], module_id: str, stage: str, skill: str) -> dict[str, Any]:
    module = next((item for item in modules if item["id"] == module_id), None)
    if module is None:
        raise ValueError(f"Unknown module: {module_id}")
    if stage not in {item["id"] for item in module["registry"].get("stages", [])}:
        raise ValueError(f"Unknown stage for {module_id}: {stage}")

    def mutate(profile: dict[str, Any]) -> dict[str, Any]:
        if skill not in _installed_map(profile):
            raise ValueError(f"Cannot bind missing, disabled, or conflicted skill: {skill}")
        key = f"{module_id}:{stage}"
        binding = profile.setdefault("bindings", {}).setdefault(key, {"manual": [], "automatic": []})
        if skill not in binding["manual"]:
            binding["manual"].insert(0, skill)
        return {"updated": True, "binding": key, "skill": skill, "state_path": str(state_path)}

    return update_profile(state_path, mutate)


def record_resolution(
    state_path: Path,
    module_id: str,
    stage: str,
    skill: str,
    action: str,
    replacement: str | None = None,
    modules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if action not in {"replace", "fallback", "disable", "clear"}:
        raise ValueError(f"Unsupported resolution action: {action}")
    if modules is not None:
        module = next((item for item in modules if item.get("id") == module_id), None)
        if module is None:
            raise ValueError(f"Unknown module: {module_id}")
        registry = module["registry"]
        if stage not in {item.get("id") for item in registry.get("stages", [])}:
            raise ValueError(f"Unknown stage for {module_id}: {stage}")
        candidates = {
            candidate
            for pipeline in registry.get("pipelines", [])
            for entry in pipeline.get("stages", [])
            if entry.get("stage") == stage
            for candidate in entry.get("candidate_skills", [])
        }
        if skill not in candidates:
            raise ValueError(f"Skill {skill} is not a declared candidate for {module_id}:{stage}")
    key = _resolution_key(module_id, stage, skill)

    def mutate(profile: dict[str, Any]) -> dict[str, Any]:
        installed = _installed_map(profile)
        if action == "replace":
            if not replacement:
                raise ValueError("--replacement is required for action=replace")
            if replacement not in installed:
                raise ValueError(f"Replacement is not installed or enabled: {replacement}")
        if action == "clear":
            profile.setdefault("resolutions", {}).pop(key, None)
        else:
            profile.setdefault("resolutions", {})[key] = {
                "action": action,
                "replacement": replacement,
                "updated_at": utc_now(),
            }
        return {"updated": True, "key": key, "action": action, "replacement": replacement, "state_path": str(state_path)}

    return update_profile(state_path, mutate)


def record_feedback(state_path: Path, skill: str, outcome: str, prompt: str = "", module: str = "", stage: str = "") -> dict[str, Any]:
    if outcome not in {"success", "failure"}:
        raise ValueError("outcome must be success or failure")
    def mutate(profile: dict[str, Any]) -> dict[str, Any]:
        if skill not in _installed_map(profile):
            raise ValueError(f"Cannot record feedback for a missing, disabled, or conflicted skill: {skill}")
        stats = profile.setdefault("feedback", {}).setdefault(skill, {"success": 0, "failure": 0})
        stats[outcome] = int(stats.get(outcome, 0)) + 1
        event = {
            "at": utc_now(),
            "skill": skill,
            "outcome": outcome,
            "module": module,
            "stage": stage,
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16] if prompt else "",
        }
        profile.setdefault("history", []).append(event)
        profile["history"] = profile["history"][-MAX_HISTORY:]
        return {"updated": True, "skill": skill, "feedback": dict(stats), "state_path": str(state_path)}

    return update_profile(state_path, mutate)


def record_conflict_preference(state_path: Path, skill: str, path: str) -> dict[str, Any]:
    chosen = str(canonical(Path(path)))

    def mutate(profile: dict[str, Any]) -> dict[str, Any]:
        conflict = next((item for item in profile.get("conflicts", []) if item.get("name") == skill), None)
        if conflict is None:
            raise ValueError(f"No duplicate-name conflict found for: {skill}")
        choices = {os.path.normcase(str(canonical(Path(item)))) for item in conflict.get("paths", [])}
        if os.path.normcase(chosen) not in choices:
            raise ValueError(f"Path is not a discovered variant for {skill}: {chosen}")
        preferences = profile.setdefault("preferences", {})
        preferences.setdefault("disabled_skills", [])
        preferences.setdefault("preferred_paths", {})[skill] = chosen
        return {"updated": True, "skill": skill, "preferred_path": chosen, "state_path": str(state_path)}

    return update_profile(state_path, mutate)


def string_list_errors(value: Any, label: str, *, required: bool = False) -> tuple[list[str], list[str]]:
    if value is None and not required:
        return [], []
    if not isinstance(value, list) or (required and not value):
        return [], [f"{label} must be a {'non-empty ' if required else ''}list"]
    strings = [item for item in value if isinstance(item, str) and item.strip()]
    errors = [] if len(strings) == len(value) else [f"{label} must contain only non-empty strings"]
    return strings, errors


def dict_list_errors(value: Any, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(value, list):
        return [], [f"{label} must be a list"]
    items = [item for item in value if isinstance(item, dict)]
    errors = [] if len(items) == len(value) else [f"{label} must contain only objects"]
    return items, errors


def collect_string_identifiers(items: list[dict[str, Any]], field: str, label: str, source: str) -> tuple[list[str], list[str]]:
    values: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(items):
        value = item.get(field)
        if isinstance(value, str) and value:
            values.append(value)
        else:
            errors.append(f"{source}: {label}[{index}].{field} must be a non-empty string")
    if len(values) != len(set(values)):
        errors.append(f"{source}: duplicate {label} identifiers")
    return values, errors


def validate_registry(registry: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(registry, dict):
        return [f"{source}: registry must contain a JSON object"]
    version = registry.get("version")
    if not isinstance(version, int) or version < 3:
        errors.append(f"{source}: version must be an integer >= 3")
    if not isinstance(registry.get("router"), str) or not registry.get("router"):
        errors.append(f"{source}: missing router")
    layers, layer_type_errors = dict_list_errors(registry.get("layers", []), f"{source}: layers")
    skills, skill_type_errors = dict_list_errors(registry.get("skills", []), f"{source}: skills")
    stages, stage_type_errors = dict_list_errors(registry.get("stages", []), f"{source}: stages")
    pipelines, pipeline_type_errors = dict_list_errors(registry.get("pipelines", []), f"{source}: pipelines")
    errors.extend(layer_type_errors + skill_type_errors + stage_type_errors + pipeline_type_errors)
    layer_ids, layer_id_errors = collect_string_identifiers(layers, "id", "layer", source)
    skill_names, skill_name_errors = collect_string_identifiers(skills, "name", "skill", source)
    stage_ids, stage_id_errors = collect_string_identifiers(stages, "id", "stage", source)
    pipeline_ids, pipeline_id_errors = collect_string_identifiers(pipelines, "id", "pipeline", source)
    errors.extend(layer_id_errors + skill_name_errors + stage_id_errors + pipeline_id_errors)
    skill_stages: dict[str, set[str]] = {}
    for item in skills:
        name = item.get("name")
        declared_stages, declared_errors = string_list_errors(item.get("stages"), f"{source}: skill {name} stages", required=True)
        errors.extend(declared_errors)
        if isinstance(name, str):
            skill_stages[name] = set(declared_stages)
    skill_parallel = {item.get("name"): bool(item.get("parallel_safe", False)) for item in skills if isinstance(item.get("name"), str)}
    layer_set = set(layer_ids)
    stage_set = set(stage_ids)
    skill_set = set(skill_names)
    for layer in layers:
        layer_id = layer.get("id")
        for field in ("label", "purpose"):
            if not isinstance(layer.get(field), str) or not layer.get(field):
                errors.append(f"{source}: layer {layer_id}.{field} must be a non-empty string")
    for stage in stages:
        if not isinstance(stage.get("id"), str) or not isinstance(stage.get("layer"), str):
            errors.append(f"{source}: stage entries must have string id and layer")
            continue
        if not isinstance(stage.get("purpose"), str) or not stage.get("purpose"):
            errors.append(f"{source}: stage {stage.get('id')}.purpose must be a non-empty string")
        if stage.get("layer") not in layer_set:
            errors.append(f"{source}: stage {stage.get('id')} references unknown layer {stage.get('layer')}")
    for skill in skills:
        name = skill.get("name")
        if not isinstance(name, str) or not isinstance(skill.get("layer"), str):
            errors.append(f"{source}: skill entries must have string name and layer")
            continue
        for field in ("priority", "category", "use_when", "install_hint"):
            if not isinstance(skill.get(field), str) or not skill.get(field):
                errors.append(f"{source}: skill {name}.{field} must be a non-empty string")
        if skill.get("layer") not in layer_set:
            errors.append(f"{source}: skill {name} references unknown layer {skill.get('layer')}")
        unknown_stages = skill_stages.get(name, set()) - stage_set
        for stage in sorted(unknown_stages):
            errors.append(f"{source}: skill {name} references unknown stage {stage}")
        if not isinstance(skill.get("parallel_safe"), bool):
            errors.append(f"{source}: skill {name} must declare boolean parallel_safe")
    for pipeline in pipelines:
        pipeline_id = pipeline.get("id")
        if not isinstance(pipeline_id, str) or not pipeline_id:
            errors.append(f"{source}: pipeline entries must have a non-empty string id")
            continue
        for field in ("label", "domain"):
            if not isinstance(pipeline.get(field), str) or not pipeline.get(field):
                errors.append(f"{source}:{pipeline_id}: {field} must be a non-empty string")
        if pipeline.get("mode") not in {"light", "default", "deep"}:
            errors.append(f"{source}:{pipeline_id}: invalid mode {pipeline.get('mode')}")
        for field in ("required_any", "intent_any", "exclude"):
            _, field_errors = string_list_errors(pipeline.get(field), f"{source}:{pipeline_id}: {field}")
            errors.extend(field_errors)
        _, trigger_errors = string_list_errors(pipeline.get("triggers"), f"{source}:{pipeline_id}: triggers", required=True)
        errors.extend(trigger_errors)
        entries, entry_errors = dict_list_errors(pipeline.get("stages", []), f"{source}:{pipeline_id}: stages")
        errors.extend(entry_errors)
        local_stages = [entry.get("stage") for entry in entries if isinstance(entry.get("stage"), str)]
        if len(local_stages) != len(set(local_stages)):
            errors.append(f"{source}:{pipeline_id}: duplicate stage entries")
        local_step = {
            entry.get("stage"): entry.get("step", 0)
            for entry in entries
            if isinstance(entry.get("stage"), str)
        }
        graph: dict[str, list[str]] = {stage: [] for stage in local_stages if stage}
        for entry in entries:
            stage = entry.get("stage")
            if not isinstance(stage, str) or not stage:
                errors.append(f"{source}:{pipeline_id}: stage entry must have a non-empty string stage")
                continue
            if stage not in stage_set:
                errors.append(f"{source}:{pipeline_id}: unknown stage {stage}")
            step = entry.get("step", 0)
            if not isinstance(step, int) or step < 1:
                errors.append(f"{source}:{pipeline_id}:{stage}: step must be positive")
            execution = entry.get("execution", "serial")
            if execution not in {"serial", "parallel"}:
                errors.append(f"{source}:{pipeline_id}:{stage}: invalid execution {execution}")
            if execution == "parallel" and not entry.get("parallel_group"):
                errors.append(f"{source}:{pipeline_id}:{stage}: missing parallel_group")
            if "parallel_group" in entry and not isinstance(entry.get("parallel_group"), str):
                errors.append(f"{source}:{pipeline_id}:{stage}: parallel_group must be a string")
            if not isinstance(entry.get("agent_role"), str) or not entry.get("agent_role"):
                errors.append(f"{source}:{pipeline_id}:{stage}: agent_role must be a non-empty string")
            if "max_skills" in entry and (
                not isinstance(entry.get("max_skills"), int) or int(entry.get("max_skills", 0)) < 1
            ):
                errors.append(f"{source}:{pipeline_id}:{stage}: max_skills must be a positive integer")
            dependencies, dependency_errors = string_list_errors(entry.get("depends_on"), f"{source}:{pipeline_id}:{stage}: depends_on")
            errors.extend(dependency_errors)
            for dependency in dependencies:
                if dependency not in local_stages:
                    errors.append(f"{source}:{pipeline_id}:{stage}: missing dependency {dependency}")
                elif dependency == stage:
                    errors.append(f"{source}:{pipeline_id}:{stage}: self dependency")
                elif local_step.get(dependency, 0) >= step:
                    errors.append(f"{source}:{pipeline_id}:{stage}: dependency {dependency} is not in an earlier step")
                graph.setdefault(stage, []).append(dependency)
            candidate_skills, candidate_errors = string_list_errors(
                entry.get("candidate_skills"),
                f"{source}:{pipeline_id}:{stage}: candidate_skills",
            )
            errors.extend(candidate_errors)
            for skill in candidate_skills:
                if skill not in skill_set:
                    errors.append(f"{source}:{pipeline_id}:{stage}: unknown skill {skill}")
                elif stage not in skill_stages.get(skill, set()):
                    errors.append(f"{source}:{pipeline_id}:{stage}: skill {skill} does not declare this stage")
                elif execution == "parallel" and not skill_parallel.get(skill, False):
                    errors.append(f"{source}:{pipeline_id}:{stage}: skill {skill} is not parallel_safe")
            conditions = entry.get("candidate_conditions", {})
            if conditions is None:
                conditions = {}
            if not isinstance(conditions, dict):
                errors.append(f"{source}:{pipeline_id}:{stage}: candidate_conditions must be an object")
                conditions = {}
            for candidate, phrases in conditions.items():
                if not isinstance(candidate, str):
                    errors.append(f"{source}:{pipeline_id}:{stage}: condition keys must be strings")
                    continue
                _, condition_errors = string_list_errors(phrases, f"{source}:{pipeline_id}:{stage}: condition for {candidate}", required=True)
                errors.extend(condition_errors)
            condition_keys = {key for key in conditions if isinstance(key, str)}
            unknown_conditions = condition_keys - set(candidate_skills)
            for skill in sorted(unknown_conditions):
                errors.append(f"{source}:{pipeline_id}:{stage}: condition for undeclared candidate {skill}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                errors.append(f"{source}:{pipeline_id}: dependency cycle at {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
    return errors


def validate_all(skill_root: Path, modules_path: Path, state_path: Path) -> dict[str, Any]:
    modules_data = load_json(modules_path, {"modules": []})
    errors: list[str] = []
    module_errors = validate_module_registry_data(modules_data, str(modules_path))
    if module_errors:
        return {"ok": False, "modules": 0, "errors": module_errors, "state_path": str(state_path)}
    seen: set[str] = set()
    validated = 0
    for module in modules_data.get("modules", []):
        module_id = module.get("id")
        if not module_id:
            errors.append("module missing id")
            continue
        if module_id in seen:
            errors.append(f"duplicate module id: {module_id}")
        seen.add(module_id)
        if not module.get("enabled", True):
            continue
        registry_path = resolve_module_path(skill_root, module.get("registry_path", ""))
        registry = load_json(registry_path, None)
        if registry is None:
            errors.append(f"{module_id}: missing registry {registry_path}")
            continue
        errors.extend(validate_registry(registry, str(registry_path)))
        validated += 1
    if state_path.exists():
        try:
            profile = read_profile(state_path)
            for item in profile.get("catalog", []):
                if item.get("enabled", True) and not Path(item["skill_file"]).exists():
                    errors.append(f"stale catalog entry: {item['name']} -> {item['skill_file']}")
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    return {"ok": not errors, "modules": validated, "errors": errors, "state_path": str(state_path)}
