from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import SchemaError
from .lark import LarkBaseClient


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    type: int
    property: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"field_name": self.name, "type": self.type}
        if self.property is not None:
            payload["property"] = self.property
        return payload


RESULT_OPTIONS = {
    "options": [
        {"name": "未执行", "color": 0},
        {"name": "通过", "color": 2},
        {"name": "失败", "color": 1},
        {"name": "阻塞", "color": 4},
        {"name": "不适用", "color": 3},
    ]
}


FIELDS = (
    FieldDefinition("用例ID", 1),
    FieldDefinition("Date", 5),
    FieldDefinition("Attachment", 17),
    FieldDefinition("需求ID", 1),
    FieldDefinition("meegle feature", 1),
    FieldDefinition("模块", 1),
    FieldDefinition("用例标题", 1),
    FieldDefinition("前置条件", 1),
    FieldDefinition("测试步骤", 1),
    FieldDefinition("预期结果", 1),
    FieldDefinition(
        "优先级",
        3,
        {"options": [{"name": "P0", "color": 1}, {"name": "P1", "color": 4}, {"name": "P2", "color": 0}, {"name": "P3", "color": 3}]},
    ),
    FieldDefinition("提测顺序", 2, {"formatter": "0"}),
    FieldDefinition("开发人员", 11, {"multiple": True}),
    FieldDefinition("测试结果", 3, RESULT_OPTIONS),
    FieldDefinition("实际结果/备注", 1),
)


@dataclass(frozen=True)
class SchemaPlan:
    table_id: str
    existing: tuple[str, ...]
    missing: tuple[FieldDefinition, ...]
    mismatched: tuple[str, ...]
    field_updates: tuple[FieldDefinition, ...]
    primary_rename_field_id: str | None

    @property
    def valid(self) -> bool:
        return (
            not self.missing
            and not self.mismatched
            and not self.field_updates
            and self.primary_rename_field_id is None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "existing": list(self.existing),
            "missing": [field.name for field in self.missing],
            "mismatched": list(self.mismatched),
            "field_updates": [field.name for field in self.field_updates],
            "primary_needs_rename": self.primary_rename_field_id is not None,
            "valid": self.valid,
        }


class SchemaManager:
    def __init__(self, lark: LarkBaseClient):
        self.lark = lark

    def plan(self, app_token: str, table_id: str) -> SchemaPlan:
        fields = self.lark.list_fields(app_token, table_id)
        by_name = {str(field.get("field_name")): field for field in fields}
        missing: list[FieldDefinition] = []
        mismatched: list[str] = []
        field_updates: list[FieldDefinition] = []
        primary_rename: str | None = None
        for definition in FIELDS:
            found = by_name.get(definition.name)
            if found is None:
                if definition.name == "用例ID":
                    primary = [field for field in fields if field.get("is_primary")]
                    if len(primary) == 1 and int(primary[0].get("type", -1)) == 1:
                        primary_rename = str(primary[0].get("field_id", ""))
                    else:
                        missing.append(definition)
                else:
                    missing.append(definition)
            elif int(found.get("type", -1)) != definition.type:
                mismatched.append(
                    f"{definition.name}: expected type {definition.type}, got {found.get('type')}"
                )
            else:
                if definition.name == "用例ID" and not found.get("is_primary"):
                    mismatched.append("用例ID must be the primary field")
                problem = _property_problem(definition, found)
                if problem:
                    field_updates.append(definition)
        return SchemaPlan(
            table_id=table_id,
            existing=tuple(sorted(by_name)),
            missing=tuple(missing),
            mismatched=tuple(mismatched),
            field_updates=tuple(field_updates),
            primary_rename_field_id=primary_rename,
        )

    def apply(self, app_token: str, table_id: str) -> SchemaPlan:
        plan = self.plan(app_token, table_id)
        if plan.mismatched:
            raise SchemaError("Lark field type mismatch: " + "; ".join(plan.mismatched))
        if plan.primary_rename_field_id:
            if self.lark.record_count(app_token, table_id) != 0:
                raise SchemaError(
                    "Cannot rename the primary field to 用例ID because the target table is not empty"
                )
            self.lark.update_field(
                app_token,
                table_id,
                plan.primary_rename_field_id,
                next(field for field in FIELDS if field.name == "用例ID").payload(),
            )
        for definition in plan.missing:
            if definition.name != "用例ID":
                self.lark.create_field(app_token, table_id, definition.payload())
        if plan.field_updates:
            current_fields = {
                str(field.get("field_name")): field
                for field in self.lark.list_fields(app_token, table_id)
            }
            for definition in plan.field_updates:
                found = current_fields.get(definition.name)
                field_id = str(found.get("field_id", "")) if found else ""
                if not field_id:
                    raise SchemaError(f"Cannot update Lark field {definition.name!r}: missing field_id")
                self.lark.update_field(
                    app_token, table_id, field_id, definition.payload()
                )
        final = self.plan(app_token, table_id)
        if not final.valid:
            raise SchemaError("Lark schema remains incomplete after apply: " + str(final.to_dict()))
        return final

    def assert_valid(self, app_token: str, table_id: str) -> None:
        plan = self.plan(app_token, table_id)
        if not plan.valid:
            raise SchemaError("Lark schema is not ready: " + str(plan.to_dict()))


def _property_problem(definition: FieldDefinition, found: dict[str, Any]) -> str | None:
    expected = definition.property or {}
    actual = found.get("property") if isinstance(found.get("property"), dict) else {}
    if definition.type == 3:
        expected_names = {str(option["name"]) for option in expected.get("options", [])}
        actual_names = {
            str(option.get("name"))
            for option in actual.get("options", [])
            if isinstance(option, dict) and option.get("name") is not None
        }
        missing = sorted(expected_names - actual_names)
        if missing:
            return "missing select options " + ", ".join(missing)
    if definition.type == 11 and bool(actual.get("multiple", True)) != bool(expected.get("multiple")):
        return "company member multi-select setting differs from the template"
    return None
