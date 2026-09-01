import tempfile
import unittest
from pathlib import Path

from dms_test_ledger.execution import CaseLedger


def record(record_id, **fields):
    return {"record_id": record_id, "fields": fields}


class FakeLark:
    def __init__(self, records):
        self.records = records
        self.updated_fields = []
        self.uploaded = []

    def resolve_target(self):
        return "app", "table"

    def list_records(self, app_token, table_id):
        return self.records

    def batch_update(self, app_token, table_id, updates, *, client_token=None):
        self.updated_fields.extend(updates)
        for update in updates:
            found = next(row for row in self.records if row["record_id"] == update["record_id"])
            found["fields"].update(update["fields"])
        return updates

    def get_record(self, app_token, table_id, record_id):
        return next(row for row in self.records if row["record_id"] == record_id)

    def upload_bitable_attachment(self, app_token, path):
        token = "file-" + path.name
        self.uploaded.append(token)
        return token

    def append_attachment(self, app_token, table_id, record_id, file_token):
        found = self.get_record(app_token, table_id, record_id)
        attachments = found["fields"].setdefault("Attachment", [])
        attachments.append({"file_token": file_token})
        return attachments


class CaseLedgerTests(unittest.TestCase):
    def setUp(self):
        self.lark = FakeLark(
            [
                record(
                    "rec2",
                    用例ID="TC-2",
                    模块="订单",
                    用例标题="第二条",
                    提测顺序=2,
                    测试结果="未执行",
                ),
                record(
                    "rec1",
                    用例ID="TC-1",
                    模块="订单",
                    用例标题="第一条",
                    提测顺序=1,
                    测试结果="未执行",
                    测试步骤="1. 执行",
                    预期结果="1. 成功",
                ),
            ]
        )
        self.ledger = CaseLedger(self.lark)

    def test_next_submission_case_uses_submission_order(self):
        result = self.ledger.next_submission_case()
        self.assertEqual("TC-1", result["fields"]["用例ID"])

    def test_record_result_only_updates_execution_fields(self):
        result = self.ledger.record_result("TC-1", "passed", notes="符合预期")
        self.assertTrue(result["verified"])
        fields = self.lark.updated_fields[0]["fields"]
        self.assertEqual({"Date", "测试结果", "实际结果/备注"}, set(fields))
        self.assertNotIn("测试步骤", fields)

    def test_failed_result_requires_evidence_or_reason(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.ledger.record_result("TC-1", "failed", notes="按钮报错")

    def test_failed_result_uploads_and_verifies_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "failure.png"
            evidence.write_bytes(b"image")
            result = self.ledger.record_result(
                "TC-1",
                "failed",
                notes="按钮报错",
                evidence=(evidence,),
            )
        self.assertEqual(1, result["evidence_added"])
        self.assertEqual(["file-failure.png"], self.lark.uploaded)


if __name__ == "__main__":
    unittest.main()
