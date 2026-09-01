import json
import tempfile
import unittest
from pathlib import Path

from dms_test_ledger.errors import ManifestError
from dms_test_ledger.manifest import archive_manifest, file_sha256, parse_manifest, verify_source_documents


def valid_manifest():
    return {
        "schema_version": "dms-test-ledger/v1",
        "product": "DMS",
        "version": "v1.2",
        "meegle_feature": "线索管理",
        "build": "2026.08.05",
        "default_environment": "DEV",
        "source_documents": [
            {"name": "prd.md", "path": "D:/requirements/prd.md", "sha256": "a" * 64}
        ],
        "requirements": [
            {
                "requirement_id": "REQ-1",
                "module": "线索",
                "title": "创建线索",
                "acceptance_criteria": ["保存后列表可见"],
                "source_locator": "prd.md#创建线索",
                "needs_clarification": False,
            }
        ],
        "test_cases": [
            {
                "case_id": "TC-1",
                "requirement_ids": ["REQ-1"],
                "module": "线索",
                "title": "创建有效线索",
                "preconditions": ["用户已登录"],
                "steps": [
                    {"action": "填写有效信息并保存", "expected": "保存成功且列表可见"}
                ],
                "priority": "P0",
                "smoke_order": 1,
                "developer_open_ids": ["ou_developer1"],
                "tester_open_ids": [],
            }
        ],
        "generation": {
            "batch_id": "batch-001",
            "generator": "Codex",
            "generated_at": "2026-08-05T10:00:00+10:00",
            "rules_version": "e2e-v1",
        },
    }


class ManifestTests(unittest.TestCase):
    def test_valid_manifest_builds_simple_lark_fields(self):
        manifest = parse_manifest(valid_manifest())
        case = manifest.test_cases[0]
        fields = case.create_fields(manifest.meegle_feature)
        self.assertEqual("TC-1", fields["用例ID"])
        self.assertEqual("线索管理", fields["meegle feature"])
        self.assertEqual(1, fields["提测顺序"])
        self.assertEqual("未执行", fields["测试结果"])
        self.assertNotIn("版本", fields)
        self.assertNotIn("开发自测", fields)
        self.assertEqual([{"id": "ou_developer1"}], fields["开发人员"])
        self.assertNotIn("生成批次", fields)

    def test_rejects_orphan_requirement(self):
        raw = valid_manifest()
        raw["test_cases"][0]["requirement_ids"] = ["REQ-NOT-FOUND"]
        with self.assertRaisesRegex(ManifestError, "unknown requirement_id"):
            parse_manifest(raw)

    def test_rejects_non_contiguous_smoke_order(self):
        raw = valid_manifest()
        raw["test_cases"][0]["smoke_order"] = 2
        with self.assertRaisesRegex(ManifestError, "contiguous from 1"):
            parse_manifest(raw)

    def test_clarification_case_cannot_enter_submission_suite(self):
        raw = valid_manifest()
        raw["requirements"][0]["needs_clarification"] = True
        with self.assertRaisesRegex(ManifestError, "cannot enter the submission suite"):
            parse_manifest(raw)

    def test_reusable_manifest_accepts_project_environment(self):
        raw = valid_manifest()
        raw["default_environment"] = "UAT"
        manifest = parse_manifest(raw)
        self.assertEqual("UAT", manifest.default_environment)

    def test_accepts_generic_schema_version(self):
        raw = valid_manifest()
        raw["schema_version"] = "lark-test-ledger/v1"
        manifest = parse_manifest(raw)
        self.assertEqual("lark-test-ledger/v1", manifest.schema_version)

    def test_accepts_multiple_company_people(self):
        raw = valid_manifest()
        raw["test_cases"][0]["developer_open_ids"] = ["ou_one", "ou_two"]
        manifest = parse_manifest(raw)
        self.assertEqual(("ou_one", "ou_two"), manifest.test_cases[0].developer_open_ids)

    def test_archive_is_immutable(self):
        manifest = parse_manifest(valid_manifest())
        with tempfile.TemporaryDirectory() as directory:
            target = archive_manifest(manifest, Path(directory))
            self.assertTrue(target.is_file())
            self.assertEqual(target, archive_manifest(manifest, Path(directory)))
            changed = valid_manifest()
            changed["product"] = "Changed"
            changed_manifest = parse_manifest(changed)
            changed_manifest = changed_manifest.__class__(
                **{**changed_manifest.__dict__, "product": manifest.product}
            )
            with self.assertRaisesRegex(ManifestError, "different content"):
                archive_manifest(changed_manifest, Path(directory))

    def test_source_hash_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "prd.md"
            source.write_text("requirement", encoding="utf-8")
            raw = valid_manifest()
            raw["source_documents"][0] = {
                "name": source.name,
                "path": str(source),
                "sha256": file_sha256(source),
            }
            verify_source_documents(parse_manifest(raw))
            source.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "hash mismatch"):
                verify_source_documents(parse_manifest(raw))

    def test_accepts_html_prototype_as_source(self):
        raw = valid_manifest()
        raw["source_documents"][0]["path"] = "D:/requirements/prototype.html"
        manifest = parse_manifest(raw)
        self.assertEqual("D:/requirements/prototype.html", manifest.source_documents[0].path)


if __name__ == "__main__":
    unittest.main()
