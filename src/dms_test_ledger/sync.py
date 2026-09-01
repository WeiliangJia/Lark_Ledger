from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from .errors import LedgerError, LarkApiError
from .lark import LarkBaseClient
from .manifest import LedgerManifest, TestCase, archive_manifest
from .schema import SchemaManager
from .state import StateStore


DEFINITION_FIELDS = (
    "用例ID",
    "需求ID",
    "meegle feature",
    "模块",
    "用例标题",
    "前置条件",
    "测试步骤",
    "预期结果",
    "优先级",
    "提测顺序",
)


@dataclass(frozen=True)
class SyncPlan:
    creates: tuple[dict[str, Any], ...]
    updates: tuple[dict[str, Any], ...]
    unchanged: int
    stale_keys: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "create": len(self.creates),
            "update": len(self.updates),
            "unchanged": self.unchanged,
            "stale_not_deleted": len(self.stale_keys),
            "stale_keys": list(self.stale_keys[:50]),
        }


class SyncEngine:
    def __init__(
        self,
        *,
        lark: LarkBaseClient,
        schema: SchemaManager,
        state: StateStore,
        archive_dir,
        batch_size: int = 200,
    ):
        self.lark = lark
        self.schema = schema
        self.state = state
        self.archive_dir = archive_dir
        self.batch_size = batch_size

    def plan(self, manifest: LedgerManifest) -> tuple[str, str, SyncPlan]:
        app_token, table_id = self.lark.resolve_target()
        self.schema.assert_valid(app_token, table_id)
        records = self.lark.list_records(app_token, table_id)
        return app_token, table_id, build_plan(manifest, records)

    def commit(self, manifest: LedgerManifest) -> dict[str, Any]:
        app_token, table_id = self.lark.resolve_target()
        self.schema.assert_valid(app_token, table_id)
        recovered = self.recover_pending(app_token, table_id)
        records = self.lark.list_records(app_token, table_id)
        plan = build_plan(manifest, records)
        archive_path = archive_manifest(manifest, self.archive_dir)

        created = self._submit_batches(
            app_token, table_id, "create", list(plan.creates), key_field="用例ID"
        )
        updated = self._submit_batches(
            app_token, table_id, "update", list(plan.updates), key_field="用例ID"
        )
        return {
            **plan.summary(),
            "created": created,
            "updated": updated,
            "recovered_batches": recovered,
            "archive": str(archive_path),
        }

    def recover_pending(self, app_token: str, table_id: str) -> int:
        recovered = 0
        for pending in self.state.pending():
            if pending["table_id"] != table_id:
                raise LedgerError(
                    f"Pending batch {pending['batch_id']} belongs to another table; reconcile it first"
                )
            try:
                if pending["operation"] == "create":
                    self.lark.batch_create(
                        app_token,
                        table_id,
                        pending["payload"],
                        client_token=pending["client_token"],
                    )
                elif pending["operation"] == "update":
                    self.lark.batch_update(
                        app_token,
                        table_id,
                        pending["payload"],
                        client_token=pending["client_token"],
                    )
                else:
                    raise LedgerError(f"Unknown pending operation: {pending['operation']}")
            except LarkApiError:
                if not self._batch_is_reconciled(
                    app_token,
                    table_id,
                    pending["operation"],
                    pending["payload"],
                    pending["keys"],
                ):
                    raise
            self.state.confirm_pending(pending["batch_id"])
            recovered += 1
        return recovered

    def _submit_batches(
        self,
        app_token: str,
        table_id: str,
        operation: str,
        records: list[dict[str, Any]],
        *,
        key_field: str,
    ) -> int:
        submitted = 0
        for offset in range(0, len(records), self.batch_size):
            batch = records[offset : offset + self.batch_size]
            batch_id = f"ledger-{operation}-{uuid.uuid4()}"
            client_token = str(uuid.uuid4())
            keys = [
                _record_key(str(item.get("fields", {}).get(key_field, "")))
                for item in batch
            ]
            self.state.save_pending(
                batch_id=batch_id,
                table_id=table_id,
                operation=operation,
                client_token=client_token,
                payload=batch,
                keys=keys,
            )
            try:
                if operation == "create":
                    self.lark.batch_create(
                        app_token, table_id, batch, client_token=client_token
                    )
                else:
                    self.lark.batch_update(
                        app_token, table_id, batch, client_token=client_token
                    )
            except LarkApiError:
                if not self._batch_is_reconciled(app_token, table_id, operation, batch, keys):
                    raise
            self.state.confirm_pending(batch_id)
            submitted += len(batch)
        return submitted

    def _batch_is_reconciled(
        self,
        app_token: str,
        table_id: str,
        operation: str,
        payload: list[dict[str, Any]],
        keys: list[str],
    ) -> bool:
        current = _index_records(self.lark.list_records(app_token, table_id))
        if operation == "create":
            return all(key in current for key in keys)
        for desired in payload:
            fields = desired.get("fields", {})
            key = _record_key(_text_value(fields.get("用例ID")))
            found = current.get(key)
            if found is None or not _fields_match(found.get("fields", {}), fields):
                return False
        return True


def build_plan(manifest: LedgerManifest, records: list[dict[str, Any]]) -> SyncPlan:
    index = _index_records(records)
    creates: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    unchanged = 0
    manifest_keys: set[str] = set()
    for case in manifest.test_cases:
        key = _record_key(case.case_id)
        manifest_keys.add(key)
        desired = case.definition_fields(manifest.meegle_feature)
        existing = index.get(key)
        if existing is None:
            creates.append({"fields": case.create_fields(manifest.meegle_feature)})
            continue
        existing_fields = existing.get("fields", {})
        changed = {
            name: value
            for name, value in desired.items()
            if not _values_equal(existing_fields.get(name), value)
        }
        changed.update(_person_assignments_if_blank(case, existing_fields))
        if changed:
            # Include the natural key in update payloads so a lost response can be
            # reconciled without relying on the local record-id mapping.
            changed["用例ID"] = case.case_id
            updates.append(
                {
                    "record_id": str(existing.get("record_id") or existing.get("id")),
                    "fields": changed,
                }
            )
        else:
            unchanged += 1
    stale = tuple(sorted(key for key in index if key not in manifest_keys))
    return SyncPlan(tuple(creates), tuple(updates), unchanged, stale)


def _person_assignments_if_blank(case: TestCase, existing: dict[str, Any]) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    if case.developer_open_ids and not existing.get("开发人员"):
        assignments["开发人员"] = [{"id": value} for value in case.developer_open_ids]
    return assignments


def _index_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for record in records:
        fields = record.get("fields", {})
        case_id = _text_value(fields.get("用例ID"))
        if not case_id:
            continue
        key = _record_key(case_id)
        if key in index:
            duplicates.append(key)
        index[key] = record
    if duplicates:
        raise LedgerError("Duplicate use-case IDs in Lark: " + ", ".join(sorted(set(duplicates))))
    return index


def _record_key(case_id: str) -> str:
    return case_id.strip()


def _fields_match(actual: dict[str, Any], desired: dict[str, Any]) -> bool:
    return all(_values_equal(actual.get(name), value) for name, value in desired.items())


def _values_equal(actual: Any, desired: Any) -> bool:
    if desired is None:
        return actual in (None, "", [])
    if isinstance(desired, str):
        return _text_value(actual) == desired
    if isinstance(desired, (int, float)) and not isinstance(desired, bool):
        try:
            return float(actual) == float(desired)
        except (TypeError, ValueError):
            return False
    return actual == desired


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("name")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts)
    return str(value)
