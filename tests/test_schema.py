import unittest

from dms_test_ledger.errors import SchemaError
from dms_test_ledger.schema import FIELDS, SchemaManager


class FakeLark:
    def __init__(self, fields, count=0):
        self.fields = fields
        self.count = count
        self.created = []
        self.updated = []

    def list_fields(self, app_token, table_id):
        return self.fields

    def record_count(self, app_token, table_id):
        return self.count

    def create_field(self, app_token, table_id, definition):
        self.created.append(definition)
        field = {**definition, "field_id": f"fld{len(self.fields)+1}", "is_primary": False}
        self.fields.append(field)
        return field

    def update_field(self, app_token, table_id, field_id, definition):
        self.updated.append((field_id, definition))
        found = next(field for field in self.fields if field["field_id"] == field_id)
        found.update(definition)
        return found


class SchemaTests(unittest.TestCase):
    def test_schema_is_one_simple_table_with_people_and_results(self):
        self.assertEqual(15, len(FIELDS))
        by_name = {field.name: field for field in FIELDS}
        self.assertEqual(5, by_name["Date"].type)
        self.assertEqual(17, by_name["Attachment"].type)
        self.assertEqual(11, by_name["开发人员"].type)
        self.assertEqual(3, by_name["测试结果"].type)
        self.assertEqual(1, by_name["meegle feature"].type)
        self.assertNotIn("版本", by_name)
        self.assertNotIn("开发自测", by_name)
        self.assertTrue(by_name["开发人员"].property["multiple"])
        self.assertFalse(any(field.type in {18, 19, 20, 21, 3001} for field in FIELDS))

    def test_apply_renames_empty_primary_and_adds_fields(self):
        lark = FakeLark(
            [{"field_id": "fldPrimary", "field_name": "文本", "type": 1, "is_primary": True}]
        )
        plan = SchemaManager(lark).apply("app", "table")
        self.assertTrue(plan.valid)
        self.assertEqual("用例ID", lark.updated[0][1]["field_name"])
        self.assertEqual(14, len(lark.created))

    def test_apply_refuses_primary_rename_on_nonempty_table(self):
        lark = FakeLark(
            [{"field_id": "fldPrimary", "field_name": "文本", "type": 1, "is_primary": True}],
            count=1,
        )
        with self.assertRaisesRegex(SchemaError, "not empty"):
            SchemaManager(lark).apply("app", "table")

    def test_apply_upgrades_people_field_to_multi_select(self):
        fields = []
        for index, definition in enumerate(FIELDS):
            payload = definition.payload()
            if definition.name == "开发人员":
                payload["property"] = {"multiple": False}
            fields.append(
                {
                    **payload,
                    "field_id": f"fld{index}",
                    "is_primary": definition.name == "用例ID",
                }
            )
        lark = FakeLark(fields)
        plan = SchemaManager(lark).plan("app", "table")
        self.assertEqual(["开发人员"], [field.name for field in plan.field_updates])
        final = SchemaManager(lark).apply("app", "table")
        self.assertTrue(final.valid)
        updated = [item for item in lark.updated if item[1]["field_name"] == "开发人员"]
        self.assertTrue(updated[0][1]["property"]["multiple"])


if __name__ == "__main__":
    unittest.main()
