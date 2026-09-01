import tempfile
import unittest
from pathlib import Path

from dms_test_ledger.errors import LedgerError, LarkApiError
from dms_test_ledger.manifest import parse_manifest
from dms_test_ledger.state import StateStore
from dms_test_ledger.sync import SyncEngine, build_plan
from test_manifest import valid_manifest


def record(record_id, **fields):
    return {"record_id": record_id, "fields": fields}


class FakeSchema:
    def assert_valid(self, app_token, table_id):
        return None


class FakeLark:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.keys = {row["fields"].get("用例ID") for row in self.records}
        self.create_calls = []
        self.update_calls = []
        self.fail_create_after_write = False

    def resolve_target(self):
        return "app", "table"

    def list_records(self, app_token, table_id):
        return self.records

    def batch_create(self, app_token, table_id, records, *, client_token=None):
        self.create_calls.append((records, client_token))
        for item in records:
            fields = dict(item["fields"])
            key = fields["用例ID"]
            if key not in self.keys:
                self.records.append(record(f"rec{len(self.records)+1}", **fields))
                self.keys.add(key)
        if self.fail_create_after_write:
            self.fail_create_after_write = False
            raise LarkApiError("response lost")
        return self.records[-len(records):]

    def batch_update(self, app_token, table_id, records, *, client_token=None):
        self.update_calls.append((records, client_token))
        for item in records:
            found = next(row for row in self.records if row["record_id"] == item["record_id"])
            found["fields"].update(item["fields"])
        return records


class SyncPlanTests(unittest.TestCase):
    def test_create_is_simple_and_defaults_results(self):
        manifest = parse_manifest(valid_manifest())
        plan = build_plan(manifest, [])
        self.assertEqual(1, len(plan.creates))
        fields = plan.creates[0]["fields"]
        self.assertEqual("未执行", fields["测试结果"])
        self.assertNotIn("版本", fields)
        self.assertNotIn("开发自测", fields)
        self.assertNotIn("内容哈希", fields)

    def test_update_never_overwrites_people_or_results(self):
        manifest = parse_manifest(valid_manifest())
        existing = record(
            "rec1",
            用例ID="TC-1",
            Date=1722470400000,
            Attachment=[{"file_token": "box-human"}],
            需求ID="REQ-1",
            模块="旧模块",
            用例标题="创建有效线索",
            前置条件="用户已登录",
            测试步骤="1. 填写有效信息并保存",
            预期结果="1. 保存成功且列表可见",
            优先级="P0",
            提测顺序=1,
            开发人员=[{"id": "ou_human"}],
            测试人员=[{"id": "ou_tester"}],
            测试结果="失败",
            **{"实际结果/备注": "人工结论"},
        )
        plan = build_plan(manifest, [existing])
        self.assertEqual(1, len(plan.updates))
        fields = plan.updates[0]["fields"]
        self.assertEqual("线索", fields["模块"])
        self.assertNotIn("Date", fields)
        self.assertNotIn("Attachment", fields)
        self.assertNotIn("开发人员", fields)
        self.assertNotIn("测试人员", fields)
        self.assertNotIn("测试结果", fields)
        self.assertNotIn("实际结果/备注", fields)

    def test_identical_case_is_unchanged(self):
        manifest = parse_manifest(valid_manifest())
        fields = manifest.test_cases[0].create_fields(manifest.meegle_feature)
        plan = build_plan(manifest, [record("rec1", **fields)])
        self.assertEqual(1, plan.unchanged)
        self.assertFalse(plan.creates)
        self.assertFalse(plan.updates)

    def test_stale_case_is_reported_not_deleted(self):
        manifest = parse_manifest(valid_manifest())
        plan = build_plan(manifest, [record("rec1", 用例ID="TC-OLD")])
        self.assertEqual(("TC-OLD",), plan.stale_keys)

    def test_duplicate_lark_key_is_rejected(self):
        manifest = parse_manifest(valid_manifest())
        rows = [
            record("rec1", 用例ID="TC-1"),
            record("rec2", 用例ID="TC-1"),
        ]
        with self.assertRaisesRegex(LedgerError, "Duplicate"):
            build_plan(manifest, rows)


class SyncEngineTests(unittest.TestCase):
    def test_response_loss_is_reconciled_without_duplicate(self):
        manifest = parse_manifest(valid_manifest())
        lark = FakeLark()
        lark.fail_create_after_write = True
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory) / "state.sqlite3")
            engine = SyncEngine(
                lark=lark,
                schema=FakeSchema(),
                state=state,
                archive_dir=Path(directory) / "archive",
                batch_size=200,
            )
            result = engine.commit(manifest)
            self.assertEqual(1, result["created"])
            self.assertEqual(1, len(lark.records))
            self.assertEqual([], state.pending())

    def test_twenty_thousand_cases_are_chunked_in_batches_of_200(self):
        raw = valid_manifest()
        raw["test_cases"] = []
        for index in range(1, 20001):
            raw["test_cases"].append(
                {
                    "case_id": f"TC-{index:05d}",
                    "requirement_ids": ["REQ-1"],
                    "module": "线索",
                    "title": f"case {index}",
                    "preconditions": [],
                    "steps": [{"action": "执行", "expected": "通过"}],
                    "priority": "P1",
                    "smoke_order": 1 if index == 1 else None,
                    "developer_open_ids": [],
                    "tester_open_ids": [],
                }
            )
        manifest = parse_manifest(raw)
        lark = FakeLark()
        with tempfile.TemporaryDirectory() as directory:
            engine = SyncEngine(
                lark=lark,
                schema=FakeSchema(),
                state=StateStore(Path(directory) / "state.sqlite3"),
                archive_dir=Path(directory) / "archive",
                batch_size=200,
            )
            result = engine.commit(manifest)
        self.assertEqual(20000, result["created"])
        self.assertEqual(100, len(lark.create_calls))


if __name__ == "__main__":
    unittest.main()
