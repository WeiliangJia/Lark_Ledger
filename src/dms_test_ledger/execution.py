from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import LedgerError
from .lark import LarkBaseClient


RESULT_ALIASES = {
    "not-run": "未执行",
    "passed": "通过",
    "failed": "失败",
    "blocked": "阻塞",
    "not-applicable": "不适用",
    "未执行": "未执行",
    "通过": "通过",
    "失败": "失败",
    "阻塞": "阻塞",
    "不适用": "不适用",
}
EXECUTION_FIELDS = frozenset({"Date", "Attachment", "测试结果", "实际结果/备注"})


class CaseLedger:
    """Read test cases and update execution-only fields in one Lark Base table."""

    def __init__(self, lark: LarkBaseClient):
        self.lark = lark

    def list_cases(
        self,
        *,
        module: str | None = None,
        result: str | None = None,
        submission_only: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        app_token, table_id = self.lark.resolve_target()
        normalized_result = normalize_result(result) if result else None
        rows: list[dict[str, Any]] = []
        for record in self.lark.list_records(app_token, table_id):
            fields = record.get("fields", {})
            if not _text(fields.get("用例ID")):
                continue
            if module and _text(fields.get("模块")) != module:
                continue
            if normalized_result and _text(fields.get("测试结果")) != normalized_result:
                continue
            if submission_only and _number(fields.get("提测顺序")) is None:
                continue
            rows.append(_summary(record))
        rows.sort(key=_case_sort_key)
        return rows[:limit] if limit is not None else rows

    def get_case(self, case_id: str) -> dict[str, Any]:
        _, _, record = self._find_case(case_id)
        return _public_record(record)

    def next_submission_case(self, *, module: str | None = None) -> dict[str, Any] | None:
        candidates = self.list_cases(
            module=module,
            result="未执行",
            submission_only=True,
        )
        if not candidates:
            return None
        return self.get_case(str(candidates[0]["case_id"]))

    def record_result(
        self,
        case_id: str,
        result: str,
        *,
        notes: str | None = None,
        executed_at: datetime | None = None,
        evidence: tuple[Path, ...] = (),
        evidence_unavailable_reason: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_result(result)
        if normalized in {"失败", "阻塞"} and not (notes or "").strip():
            raise ValueError("notes are required for failed or blocked results")
        if normalized == "失败" and not evidence and not (evidence_unavailable_reason or "").strip():
            raise ValueError(
                "failed results require at least one evidence file or an evidence-unavailable reason"
            )
        app_token, table_id, record = self._find_case(case_id)
        record_id = str(record.get("record_id") or record.get("id") or "")
        if not record_id:
            raise LedgerError(f"Lark record for {case_id!r} omitted record_id")
        note_parts = []
        if notes and notes.strip():
            note_parts.append(notes.strip())
        if evidence_unavailable_reason and evidence_unavailable_reason.strip():
            note_parts.append("未能提供失败证据：" + evidence_unavailable_reason.strip())
        fields: dict[str, Any] = {
            "Date": _timestamp_ms(executed_at),
            "测试结果": normalized,
        }
        if note_parts:
            fields["实际结果/备注"] = "\n".join(note_parts)
        _assert_execution_only(fields)
        self.lark.batch_update(
            app_token,
            table_id,
            [{"record_id": record_id, "fields": fields}],
        )
        uploaded: list[str] = []
        for path in evidence:
            file_token = self.lark.upload_bitable_attachment(app_token, path)
            self.lark.append_attachment(app_token, table_id, record_id, file_token)
            uploaded.append(file_token)
        verified = self.lark.get_record(app_token, table_id, record_id)
        verified_fields = verified.get("fields", {})
        if _text(verified_fields.get("测试结果")) != normalized:
            raise LedgerError("Execution result write-back verification failed")
        if note_parts and _text(verified_fields.get("实际结果/备注")) != fields["实际结果/备注"]:
            raise LedgerError("Execution notes write-back verification failed")
        verified_tokens = {
            item.get("file_token")
            for item in verified_fields.get("Attachment", [])
            if isinstance(item, dict)
        }
        if any(token not in verified_tokens for token in uploaded):
            raise LedgerError("Execution evidence write-back verification failed")
        return {
            "recorded": True,
            "case_id": case_id,
            "record_id": record_id,
            "result": normalized,
            "evidence_added": len(uploaded),
            "verified": True,
        }

    def _find_case(self, case_id: str) -> tuple[str, str, dict[str, Any]]:
        app_token, table_id = self.lark.resolve_target()
        matches = [
            record
            for record in self.lark.list_records(app_token, table_id)
            if _text(record.get("fields", {}).get("用例ID")) == case_id
        ]
        if len(matches) != 1:
            raise LedgerError(
                f"Expected exactly one Lark record for case ID {case_id!r}; found {len(matches)}"
            )
        return app_token, table_id, matches[0]


def normalize_result(value: str) -> str:
    normalized = RESULT_ALIASES.get(value.strip().lower()) or RESULT_ALIASES.get(value.strip())
    if normalized is None:
        raise ValueError("result must be one of: " + ", ".join(sorted(RESULT_ALIASES)))
    return normalized


def _assert_execution_only(fields: dict[str, Any]) -> None:
    unexpected = sorted(set(fields) - EXECUTION_FIELDS)
    if unexpected:
        raise LedgerError("Refusing to overwrite generated case fields: " + ", ".join(unexpected))


def _timestamp_ms(value: datetime | None) -> int:
    moment = value or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", {})
    return {
        "case_id": _text(fields.get("用例ID")),
        "module": _text(fields.get("模块")),
        "title": _text(fields.get("用例标题")),
        "priority": _text(fields.get("优先级")),
        "submission_order": _number(fields.get("提测顺序")),
        "result": _text(fields.get("测试结果")) or "未执行",
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": str(record.get("record_id") or record.get("id") or ""),
        "fields": record.get("fields", {}),
    }


def _case_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    order = item.get("submission_order")
    return (order is None, float(order or 0), str(item.get("case_id", "")))


def _number(value: Any) -> float | int | None:
    if value in (None, "", []):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text") or item.get("name") or "")
            if isinstance(item, dict)
            else str(item)
            for item in value
        )
    return str(value)
