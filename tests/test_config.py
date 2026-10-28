import tempfile
import unittest
from pathlib import Path

from dms_test_ledger.config import Settings, parse_base_url, parse_target_url
from dms_test_ledger.errors import ConfigError


class ConfigTests(unittest.TestCase):
    def test_parse_base_url(self):
        app_token, table_id = parse_base_url(
            "https://example.sg.larksuite.com/base/appABC?table=tbl123&view=vew1"
        )
        self.assertEqual("appABC", app_token)
        self.assertEqual("tbl123", table_id)

    def test_parse_wiki_base_url(self):
        app_token, table_id, wiki_token = parse_target_url(
            "https://example.sg.larksuite.com/wiki/wikABC?table=tbl123&view=vew1"
        )
        self.assertIsNone(app_token)
        self.assertEqual("tbl123", table_id)
        self.assertEqual("wikABC", wiki_token)

    def test_settings_accept_external_state_and_defaults_simple_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = root / "ledger.env"
            env.write_text(
                "\n".join(
                    [
                        "LARK_APP_ID=cli_test",
                        "LARK_APP_SECRET=secret",
                        "LARK_REDIRECT_URI=http://127.0.0.1:38117/callback",
                        "LARK_BASE_URL=https://example.sg.larksuite.com/base/appABC?table=tbl123",
                        f"LEDGER_STATE_DB={root / 'state.sqlite3'}",
                        f"LARK_TOKEN_DB={root / 'tokens.sqlite3'}",
                    ]
                ),
                encoding="utf-8",
            )
            settings = Settings.from_env_file(env)
            self.assertEqual("测试用例", settings.lark_table_name)
            self.assertEqual(200, settings.batch_size)
            self.assertEqual(root / "manifests", settings.archive_dir)
            self.assertEqual(root / "tokens.sqlite3", settings.lark_token_db_path)
            workspace = Path(__file__).resolve().parents[2]
            self.assertEqual(
                workspace / ".local" / "lark-oauth-refresh.lock",
                settings.oauth_lock_path,
            )

    def test_settings_allow_create_before_base_url_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = root / "ledger.env"
            env.write_text(
                "\n".join(
                    [
                        "LARK_APP_ID=cli_test",
                        "LARK_APP_SECRET=secret",
                        "LARK_REDIRECT_URI=http://127.0.0.1:38117/callback",
                        "LARK_BASE_URL=",
                        f"LEDGER_STATE_DB={root / 'state.sqlite3'}",
                        f"LARK_TOKEN_DB={root / 'tokens.sqlite3'}",
                    ]
                ),
                encoding="utf-8",
            )
            settings = Settings.from_env_file(env, require_base_url=False)
            self.assertEqual("", settings.lark_base_url)

    def test_project_env_can_reuse_shared_identity_without_copying_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            shared = root / "shared.env"
            shared.write_text(
                "\n".join(
                    [
                        "LARK_APP_ID=shared_app",
                        "LARK_APP_SECRET=shared_secret",
                        "LARK_REDIRECT_URI=http://127.0.0.1:8765/callback",
                        "LARK_TOKEN_DB=shared-token.sqlite3",
                        "LARK_OAUTH_LOCK_PATH=shared-refresh.lock",
                    ]
                ),
                encoding="utf-8",
            )
            project_dir = root / "project"
            project_dir.mkdir()
            env = project_dir / "ledger.env"
            env.write_text(
                "\n".join(
                    [
                        "LARK_IDENTITY_ENV_FILE=../shared.env",
                        "LARK_BASE_URL=https://example.sg.larksuite.com/base/appABC?table=tbl123",
                        "LARK_TABLE_NAME=Project Cases",
                        "LEDGER_STATE_DB=state.sqlite3",
                        "LEDGER_ARCHIVE_DIR=manifests",
                    ]
                ),
                encoding="utf-8",
            )
            settings = Settings.from_env_file(env)
            self.assertEqual("shared_app", settings.lark_app_id)
            self.assertEqual("shared_secret", settings.lark_app_secret)
            self.assertEqual(project_dir / "state.sqlite3", settings.state_db_path)
            self.assertEqual(project_dir / "manifests", settings.archive_dir)
            self.assertEqual(project_dir / "shared-token.sqlite3", settings.lark_token_db_path)
            self.assertEqual(project_dir / "shared-refresh.lock", settings.oauth_lock_path)

    def test_batch_size_cannot_exceed_lark_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = root / "ledger.env"
            env.write_text(
                "\n".join(
                    [
                        "LARK_APP_ID=cli_test",
                        "LARK_APP_SECRET=secret",
                        "LARK_REDIRECT_URI=http://127.0.0.1:38117/callback",
                        "LARK_BASE_URL=https://example.sg.larksuite.com/base/appABC?table=tbl123",
                        f"LEDGER_STATE_DB={root / 'state.sqlite3'}",
                        f"LARK_TOKEN_DB={root / 'tokens.sqlite3'}",
                        "LARK_BATCH_SIZE=1001",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "between 1 and 1000"):
                Settings.from_env_file(env)

    def test_rejects_unedited_windows_user_path_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env = root / "ledger.env"
            env.write_text(
                "\n".join(
                    [
                        "LARK_APP_ID=cli_test",
                        "LARK_APP_SECRET=secret",
                        "LARK_REDIRECT_URI=http://127.0.0.1:38117/callback",
                        "LARK_BASE_URL=https://example.sg.larksuite.com/base/appABC?table=tbl123",
                        f"LEDGER_STATE_DB={root / 'state.sqlite3'}",
                        r"LARK_TOKEN_DB=C:\Users\your-name\AppData\Local\DmsLarkSync\state.sqlite3",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "template user-name placeholder"):
                Settings.from_env_file(env)


if __name__ == "__main__":
    unittest.main()
