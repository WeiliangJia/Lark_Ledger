import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from dms_test_ledger.config import Settings
from dms_test_ledger.lark import JsonHttpClient, LarkBaseClient, OAuthService, TokenManager
from dms_test_ledger.state import StateStore, TokenSet


def settings(root):
    return Settings(
        lark_app_id="app",
        lark_app_secret="secret",
        lark_redirect_uri="http://127.0.0.1:38117/callback",
        lark_oauth_scopes="offline_access bitable:app",
        lark_api_base_url="https://open.larksuite.com",
        lark_authorize_url="https://open.larksuite.com/open-apis/authen/v1/authorize",
        lark_base_url="https://example.larksuite.com/base/appABC?table=tblABC",
        lark_table_name="测试用例",
        state_db_path=root / "state.sqlite3",
        lark_token_db_path=root / "tokens.sqlite3",
        archive_dir=root / "archive",
        batch_size=200,
        request_timeout=30,
    )


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


class SequenceHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class LarkTests(unittest.TestCase):
    def test_uploads_png_as_bitable_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "DMS-TC-001-failure.png"
            screenshot.write_bytes(b"\x89PNG\r\n\x1a\nexample")
            http = FakeHttp({"code": 0, "data": {"file_token": "box-new"}})

            class Tokens:
                def get_access_token(self):
                    return "access"

            client = LarkBaseClient(settings(root), Tokens(), http)
            token = client.upload_bitable_attachment("appABC", screenshot)
            self.assertEqual("box-new", token)
            method, url, call = http.calls[0]
            self.assertEqual("POST", method)
            self.assertTrue(url.endswith("/open-apis/drive/v1/medias/upload_all"))
            self.assertIn("multipart/form-data; boundary=", call["headers"]["Content-Type"])
            raw_body = call["raw_body"]
            self.assertIn(b'parent_type\"\r\n\r\nbitable_image', raw_body)
            self.assertIn(b'parent_node\"\r\n\r\nappABC', raw_body)
            self.assertIn(b'DMS-TC-001-failure.png', raw_body)

    def test_append_attachment_preserves_existing_tokens(self):
        root = Path("D:/Star X/DMS/.tmp")
        http = SequenceHttp(
            [
                {
                    "code": 0,
                    "data": {
                        "record": {
                            "record_id": "rec1",
                            "fields": {
                                "Attachment": [
                                    {"file_token": "box-human", "name": "old.png"}
                                ]
                            },
                        }
                    },
                },
                {
                    "code": 0,
                    "data": {
                        "records": [
                            {
                                "record_id": "rec1",
                                "fields": {
                                    "Attachment": [
                                        {"file_token": "box-human"},
                                        {"file_token": "box-new"},
                                    ]
                                },
                            }
                        ]
                    },
                },
            ]
        )

        class Tokens:
            def get_access_token(self):
                return "access"

        client = LarkBaseClient(settings(root), Tokens(), http)
        attachments = client.append_attachment(
            "appABC", "tblABC", "rec1", "box-new"
        )
        self.assertEqual(
            [{"file_token": "box-human"}, {"file_token": "box-new"}],
            attachments,
        )
        method, url, call = http.calls[1]
        self.assertEqual("POST", method)
        self.assertIn("/records/batch_update", url)
        self.assertEqual(
            attachments,
            call["body"]["records"][0]["fields"]["Attachment"],
        )

    def test_creates_base_and_renames_default_table(self):
        root = Path("D:/Star X/DMS/.tmp")
        http = FakeHttp(
            {
                "code": 0,
                "data": {
                    "app": {
                        "app_token": "appNew",
                        "default_table_id": "tblNew",
                        "name": "DMS 测试用例账本",
                        "url": "https://example.larksuite.com/base/appNew",
                    }
                },
            }
        )

        class Tokens:
            def get_access_token(self):
                return "access"

        client = LarkBaseClient(settings(root), Tokens(), http)
        created = client.create_base("DMS 测试用例账本")
        self.assertEqual("appNew", created["app_token"])
        method, url, call = http.calls[0]
        self.assertEqual("POST", method)
        self.assertTrue(url.endswith("/open-apis/bitable/v1/apps"))
        self.assertEqual("Australia/Sydney", call["body"]["time_zone"])

        http.response = {"code": 0, "data": {"name": "测试用例"}}
        client.rename_table("appNew", "tblNew", "测试用例")
        method, url, call = http.calls[1]
        self.assertEqual("PATCH", method)
        self.assertTrue(url.endswith("/apps/appNew/tables/tblNew"))
        self.assertEqual({"name": "测试用例"}, call["body"])

    def test_batch_deletes_only_requested_records(self):
        root = Path("D:/Star X/DMS/.tmp")
        http = FakeHttp(
            {
                "code": 0,
                "data": {
                    "records": [
                        {"record_id": "rec1", "deleted": True},
                        {"record_id": "rec2", "deleted": True},
                    ]
                },
            }
        )

        class Tokens:
            def get_access_token(self):
                return "access"

        client = LarkBaseClient(settings(root), Tokens(), http)
        result = client.batch_delete("appNew", "tblNew", ["rec1", "rec2"])
        self.assertEqual(2, len(result))
        method, url, call = http.calls[0]
        self.assertEqual("POST", method)
        self.assertIn("/records/batch_delete", url)
        self.assertEqual({"records": ["rec1", "rec2"]}, call["body"])

    def test_can_share_existing_feedback_tool_oauth_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token_db = root / "existing-state.sqlite3"
            connection = sqlite3.connect(token_db)
            try:
                connection.execute(
                    """
                    CREATE TABLE oauth_tokens (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        access_token TEXT NOT NULL,
                        access_expires_at INTEGER NOT NULL,
                        refresh_token TEXT NOT NULL,
                        refresh_expires_at INTEGER NOT NULL,
                        scope TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO oauth_tokens VALUES(1, 'shared-access', 10, 'shared-refresh', 20, 'bitable:app', 'now')"
                )
                connection.commit()
            finally:
                connection.close()
            state = StateStore(root / "ledger-state.sqlite3", token_db_path=token_db)
            tokens = state.load_tokens()
            self.assertEqual("shared-access", tokens.access_token)
            self.assertEqual("shared-refresh", tokens.refresh_token)
            self.assertTrue((root / "ledger-state.sqlite3").is_file())

    def test_resolves_wiki_bitable_to_same_base_api_target(self):
        root = Path("C:/temp")
        configured = settings(root)
        configured = Settings(
            **{
                **configured.__dict__,
                "lark_base_url": "https://example.larksuite.com/wiki/wikABC?table=tblABC",
            }
        )

        class Client(LarkBaseClient):
            def _request(self, method, path, *, query=None, body=None):
                if path == "/open-apis/wiki/v2/spaces/get_node":
                    return {
                        "code": 0,
                        "data": {"node": {"obj_type": "bitable", "obj_token": "appResolved"}},
                    }
                if path == "/open-apis/bitable/v1/apps/appResolved/tables":
                    return {
                        "code": 0,
                        "data": {
                            "items": [{"name": "测试用例", "table_id": "tblABC"}],
                            "has_more": False,
                        },
                    }
                raise AssertionError(path)

        client = Client(configured, object(), object())
        self.assertEqual(("appResolved", "tblABC"), client.resolve_target())

    def test_http_client_retries_429(self):
        attempts = []
        error = urllib.error.HTTPError(
            "https://open.larksuite.com/test", 429, "rate", {}, None
        )
        error.read = lambda: json.dumps({"code": 1254290, "msg": "rate limited"}).encode()

        def urlopen(request, timeout):
            attempts.append(1)
            if len(attempts) == 1:
                raise error
            return FakeResponse({"code": 0, "data": {}})

        with patch("urllib.request.urlopen", side_effect=urlopen):
            result = JsonHttpClient(max_attempts=2, sleep=lambda seconds: None).request(
                "GET", "https://open.larksuite.com/test"
            )
        self.assertEqual(0, result["code"])
        self.assertEqual(2, len(attempts))

    def test_refresh_rotates_and_persists_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = StateStore(root / "state.sqlite3")
            previous = TokenSet("old-access", 1, "old-refresh", 9999999999, "offline_access")
            state.save_tokens(previous)
            http = FakeHttp(
                {
                    "code": 0,
                    "data": {
                        "access_token": "new-access",
                        "expires_in": 7200,
                        "refresh_token": "new-refresh",
                        "refresh_token_expires_in": 604800,
                        "scope": "offline_access bitable:app",
                    },
                }
            )
            service = OAuthService(settings(root), state, http)
            result = service.refresh("old-refresh", previous)
            self.assertEqual("new-refresh", result.refresh_token)
            self.assertEqual(result, state.load_tokens())
            sent = http.calls[0][2]["body"]
            self.assertEqual("old-refresh", sent["refresh_token"])

    def test_token_manager_refreshes_expired_access_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = StateStore(root / "state.sqlite3")
            state.save_tokens(TokenSet("expired", 1, "refresh", 9999999999, "offline_access"))

            class OAuth:
                def refresh(self, refresh_token, previous):
                    token = TokenSet("fresh", 9999999999, "next", 9999999999, previous.scope)
                    state.save_tokens(token)
                    return token

            self.assertEqual("fresh", TokenManager(OAuth(), state).get_access_token())


if __name__ == "__main__":
    unittest.main()
