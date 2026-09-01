from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import ManifestError


SCHEMA_VERSION = "lark-test-ledger/v1"
LEGACY_SCHEMA_VERSIONS = {"dms-test-ledger/v1"}
PRIORITIES = {"P0", "P1", "P2", "P3"}
OPEN_ID_PATTERN = re.compile(r"^ou_[A-Za-z0-9_-]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED_SOURCE_SUFFIXES = {".md", ".markdown", ".docx", ".pdf", ".xlsx", ".html", ".htm"}


@dataclass(frozen=True)
class SourceDocument:
    name: str
    path: str
    sha256: str


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    module: str
    title: str
    acceptance_criteria: tuple[str, ...]
    source_locator: str
    needs_clarification: bool


@dataclass(frozen=True)
class Step:
    action: str
    expected: str


@dataclass(frozen=True)
class TestCase:
    case_id: str
    requirement_ids: tuple[str, ...]
    module: str
    title: str
    preconditions: tuple[str, ...]
    steps: tuple[Step, ...]
    priority: str
    smoke_order: int | None
    developer_open_ids: tuple[str, ...]
    tester_open_ids: tuple[str, ...]

    def definition_fields(self, meegle_feature: str) -> dict[str, Any]:
        actions = "\n".join(f"{index}. {step.action}" for index, step in enumerate(self.steps, 1))
        expected = "\n".join(
            f"{index}. {step.expected}" for index, step in enumerate(self.steps, 1)
        )
        return {
            "用例ID": self.case_id,
            "需求ID": "、".join(self.requirement_ids),
            "meegle feature": meegle_feature,
            "模块": self.module,
            "用例标题": self.title,
            "前置条件": "\n".join(self.preconditions),
            "测试步骤": actions,
            "预期结果": expected,
            "优先级": self.priority,
            "提测顺序": self.smoke_order,
        }

    def create_fields(self, meegle_feature: str) -> dict[str, Any]:
        fields = self.definition_fields(meegle_feature)
        fields["测试结果"] = "未执行"
        if self.developer_open_ids:
            fields["开发人员"] = [{"id": value} for value in self.developer_open_ids]
        return fields


@dataclass(frozen=True)
class Generation:
    batch_id: str
    generator: str
    generated_at: str
    rules_version: str


@dataclass(frozen=True)
class LedgerManifest:
    schema_version: str
    product: str
    version: str
    meegle_feature: str
    build: str
    default_environment: str
    source_documents: tuple[SourceDocument, ...]
    requirements: tuple[Requirement, ...]
    test_cases: tuple[TestCase, ...]
    generation: Generation
    raw: dict[str, Any]

    @property
    def smoke_cases(self) -> tuple[TestCase, ...]:
        return tuple(sorted((case for case in self.test_cases if case.smoke_order), key=lambda c: c.smoke_order or 0))

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product": self.product,
            "version": self.version,
            "meegle_feature": self.meegle_feature,
            "build": self.build,
            "environment": self.default_environment,
            "source_documents": len(self.source_documents),
            "requirements": len(self.requirements),
            "test_cases": len(self.test_cases),
            "submission_cases": len(self.smoke_cases),
            "batch_id": self.generation.batch_id,
        }


def load_manifest(path: Path) -> LedgerManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cannot read manifest JSON: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be a JSON object")
    return parse_manifest(raw)


def parse_manifest(raw: dict[str, Any]) -> LedgerManifest:
    errors: list[str] = []
    schema_version = _text(raw, "schema_version", errors)
    if schema_version not in {SCHEMA_VERSION, *LEGACY_SCHEMA_VERSIONS}:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}; legacy values: {sorted(LEGACY_SCHEMA_VERSIONS)}"
        )
    product = _text(raw, "product", errors)
    version = _text(raw, "version", errors)
    meegle_feature = _text(raw, "meegle_feature", errors)
    build = _optional_text(raw.get("build"), "build", errors)
    environment = _optional_text(raw.get("default_environment", "DEV"), "default_environment", errors)
    if not environment:
        errors.append("default_environment must not be empty")

    documents: list[SourceDocument] = []
    for index, item in enumerate(_list(raw, "source_documents", errors)):
        context = f"source_documents[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context} must be an object")
            continue
        name = _text(item, "name", errors, context)
        source_path = _text(item, "path", errors, context)
        if source_path and Path(source_path).suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
            errors.append(
                f"{context}.path must use one of {sorted(SUPPORTED_SOURCE_SUFFIXES)}"
            )
        sha256 = _text(item, "sha256", errors, context).lower()
        if sha256 and not SHA256_PATTERN.fullmatch(sha256):
            errors.append(f"{context}.sha256 must be a lowercase SHA-256 hex digest")
        documents.append(SourceDocument(name=name, path=source_path, sha256=sha256))
    if not documents:
        errors.append("source_documents must contain at least one document")

    requirements: list[Requirement] = []
    requirement_ids: set[str] = set()
    for index, item in enumerate(_list(raw, "requirements", errors)):
        context = f"requirements[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context} must be an object")
            continue
        requirement_id = _text(item, "requirement_id", errors, context)
        if requirement_id in requirement_ids:
            errors.append(f"duplicate requirement_id: {requirement_id}")
        requirement_ids.add(requirement_id)
        criteria = _string_list(item.get("acceptance_criteria"), f"{context}.acceptance_criteria", errors)
        if not criteria:
            errors.append(f"{context}.acceptance_criteria must not be empty")
        requirements.append(
            Requirement(
                requirement_id=requirement_id,
                module=_text(item, "module", errors, context),
                title=_text(item, "title", errors, context),
                acceptance_criteria=criteria,
                source_locator=_text(item, "source_locator", errors, context),
                needs_clarification=_bool(item.get("needs_clarification", False), f"{context}.needs_clarification", errors),
            )
        )
    if not requirements:
        errors.append("requirements must contain at least one requirement")

    test_cases: list[TestCase] = []
    case_ids: set[str] = set()
    covered_requirements: set[str] = set()
    smoke_orders: list[int] = []
    requirements_by_id = {item.requirement_id: item for item in requirements}
    for index, item in enumerate(_list(raw, "test_cases", errors)):
        context = f"test_cases[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context} must be an object")
            continue
        case_id = _text(item, "case_id", errors, context)
        if case_id in case_ids:
            errors.append(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        linked_requirements = _string_list(item.get("requirement_ids"), f"{context}.requirement_ids", errors)
        if not linked_requirements:
            errors.append(f"{context}.requirement_ids must not be empty")
        for requirement_id in linked_requirements:
            if requirement_id not in requirement_ids:
                errors.append(f"{context} references unknown requirement_id {requirement_id!r}")
            else:
                covered_requirements.add(requirement_id)
        steps: list[Step] = []
        raw_steps = item.get("steps", [])
        if not isinstance(raw_steps, list):
            errors.append(f"{context}.steps must be an array")
            raw_steps = []
        for step_index, step in enumerate(raw_steps):
            step_context = f"{context}.steps[{step_index}]"
            if not isinstance(step, dict):
                errors.append(f"{step_context} must be an object")
                continue
            steps.append(
                Step(
                    action=_text(step, "action", errors, step_context),
                    expected=_text(step, "expected", errors, step_context),
                )
            )
        if not steps:
            errors.append(f"{context}.steps must not be empty")
        priority = _text(item, "priority", errors, context).upper()
        if priority and priority not in PRIORITIES:
            errors.append(f"{context}.priority must be one of {sorted(PRIORITIES)}")
        smoke_order = item.get("smoke_order")
        if smoke_order is not None and (not isinstance(smoke_order, int) or isinstance(smoke_order, bool) or smoke_order < 1):
            errors.append(f"{context}.smoke_order must be a positive integer or null")
            smoke_order = None
        if smoke_order is not None:
            smoke_orders.append(smoke_order)
            uncertain = [
                req_id
                for req_id in linked_requirements
                if requirements_by_id.get(req_id) and requirements_by_id[req_id].needs_clarification
            ]
            if uncertain:
                errors.append(
                    f"{context} cannot enter the submission suite because requirements need clarification: "
                    + ", ".join(uncertain)
                )
        developer_ids = _open_ids(item.get("developer_open_ids", []), f"{context}.developer_open_ids", errors)
        tester_ids = _open_ids(item.get("tester_open_ids", []), f"{context}.tester_open_ids", errors)
        test_cases.append(
            TestCase(
                case_id=case_id,
                requirement_ids=linked_requirements,
                module=_text(item, "module", errors, context),
                title=_text(item, "title", errors, context),
                preconditions=_string_list(item.get("preconditions", []), f"{context}.preconditions", errors),
                steps=tuple(steps),
                priority=priority,
                smoke_order=smoke_order,
                developer_open_ids=developer_ids,
                tester_open_ids=tester_ids,
            )
        )
    if not test_cases:
        errors.append("test_cases must contain at least one test case")
    if len(test_cases) > 20000:
        errors.append("test_cases must not exceed 20,000 items for one product Base")

    expected_orders = list(range(1, len(smoke_orders) + 1))
    if sorted(smoke_orders) != expected_orders:
        errors.append(f"smoke_order values must be contiguous from 1; got {sorted(smoke_orders)}")
    if not smoke_orders:
        errors.append("at least one test case must be included in the submission suite")

    for requirement in requirements:
        if not requirement.needs_clarification and requirement.requirement_id not in covered_requirements:
            errors.append(f"requirement {requirement.requirement_id!r} has no test case coverage")

    generation_raw = raw.get("generation")
    if not isinstance(generation_raw, dict):
        errors.append("generation must be an object")
        generation_raw = {}
    generated_at = _text(generation_raw, "generated_at", errors, "generation")
    if generated_at:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("generation.generated_at must be an ISO-8601 timestamp")
    generation = Generation(
        batch_id=_text(generation_raw, "batch_id", errors, "generation"),
        generator=_text(generation_raw, "generator", errors, "generation"),
        generated_at=generated_at,
        rules_version=_text(generation_raw, "rules_version", errors, "generation"),
    )

    if errors:
        raise ManifestError("Manifest validation failed:\n- " + "\n- ".join(errors))
    return LedgerManifest(
        schema_version=schema_version,
        product=product,
        version=version,
        meegle_feature=meegle_feature,
        build=build,
        default_environment=environment,
        source_documents=tuple(documents),
        requirements=tuple(requirements),
        test_cases=tuple(test_cases),
        generation=generation,
        raw=raw,
    )


def archive_manifest(manifest: LedgerManifest, archive_dir: Path) -> Path:
    safe_product = _safe_segment(manifest.product)
    safe_version = _safe_segment(manifest.version)
    safe_batch = _safe_segment(manifest.generation.batch_id)
    target_dir = archive_dir / safe_product / safe_version
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{safe_batch}.json"
    encoded = (json.dumps(manifest.raw, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if target.exists():
        current = target.read_bytes()
        if current != encoded:
            raise ManifestError(f"Archived batch already exists with different content: {target}")
        return target
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(target)
    return target


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source_documents(manifest: LedgerManifest) -> None:
    errors: list[str] = []
    for document in manifest.source_documents:
        path = Path(document.path)
        if not path.is_file():
            errors.append(f"source document not found: {path}")
            continue
        actual = file_sha256(path)
        if actual != document.sha256:
            errors.append(
                f"source document hash mismatch: {path} (manifest={document.sha256}, actual={actual})"
            )
    if errors:
        raise ManifestError("Source verification failed:\n- " + "\n- ".join(errors))


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "unnamed"


def _text(source: dict[str, Any], key: str, errors: list[str], context: str = "manifest") -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{context}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _optional_text(value: Any, name: str, errors: list[str]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        errors.append(f"{name} must be a string")
        return ""
    return value.strip()


def _list(source: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    value = source.get(key)
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    return value


def _string_list(value: Any, context: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        errors.append(f"{context} must be an array of strings")
        return ()
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{context}[{index}] must be a non-empty string")
        else:
            result.append(item.strip())
    return tuple(result)


def _open_ids(value: Any, context: str, errors: list[str]) -> tuple[str, ...]:
    items = _string_list(value, context, errors)
    for item in items:
        if not OPEN_ID_PATTERN.fullmatch(item):
            errors.append(f"{context} contains invalid Lark open_id {item!r}")
    return items


def _bool(value: Any, context: str, errors: list[str]) -> bool:
    if not isinstance(value, bool):
        errors.append(f"{context} must be true or false")
        return False
    return value
