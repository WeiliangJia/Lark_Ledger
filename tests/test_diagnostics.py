import unittest

from dms_test_ledger.diagnostics import run_doctor
from dms_test_ledger.errors import AuthenticationError
from dms_test_ledger.state import TokenSet


class FakeState:
    def __init__(self, tokens):
        self.tokens = tokens

    def load_tokens(self):
        return self.tokens


class FakeTokenManager:
    def __init__(self):
        self.calls = 0

    def get_access_token(self):
        self.calls += 1
        return "access"


class FakeLark:
    def __init__(self):
        self.token_manager = FakeTokenManager()

    def resolve_target(self):
        return "app", "table"

    def record_count(self, app_token, table_id):
        return 12


class FakePlan:
    valid = True

    def to_dict(self):
        return {"valid": True}


class FakeSchema:
    def plan(self, app_token, table_id):
        return FakePlan()


class DoctorTests(unittest.TestCase):
    def test_requires_authorization(self):
        with self.assertRaisesRegex(AuthenticationError, "run auth"):
            run_doctor(state=FakeState(None), lark=FakeLark(), schema=FakeSchema())

    def test_checks_token_target_and_schema_without_writing(self):
        tokens = TokenSet("access", 1, "refresh", 2, "scope")
        lark = FakeLark()
        result = run_doctor(state=FakeState(tokens), lark=lark, schema=FakeSchema())
        self.assertTrue(result["ready"])
        self.assertEqual(12, result["record_count"])
        self.assertEqual(1, lark.token_manager.calls)


if __name__ == "__main__":
    unittest.main()
