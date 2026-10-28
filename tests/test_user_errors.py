import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from dms_test_ledger.cli import main
from dms_test_ledger.errors import AuthenticationError, ConfigError, LarkApiError, ManifestError
from dms_test_ledger.user_errors import explain_error


class UserErrorTests(unittest.TestCase):
    def test_actionable_categories_and_no_remote_secret_echo(self):
        for error, expected in [
            (AuthenticationError('secret-token'), 'auth'),
            (ConfigError('secret-token'), '配置'),
            (LarkApiError('secret-token', status=403, code=123), '权限'),
            (LarkApiError('secret-token', status=429), '稍后重试'),
            (LarkApiError('network failure secret-token'), '网络'),
            (LarkApiError('secret-token'), 'doctor'),
            (PermissionError('secret-token'), '权限'),
            (FileNotFoundError('secret-token'), '路径'),
        ]:
            with self.subTest(error=type(error).__name__, expected=expected):
                message = explain_error(error)
                self.assertIn(expected, message)
                self.assertNotIn('secret-token', message)

    def test_manifest_retains_validation_detail(self):
        self.assertIn('test_cases', explain_error(ManifestError('test_cases missing')))

    def test_invalid_arguments_offer_help_in_chinese(self):
        with redirect_stderr(StringIO()) as output, self.assertRaises(SystemExit) as error:
            main(['execution', 'unknown'])
        self.assertEqual(2, error.exception.code)
        self.assertIn('命令参数不完整或无效', output.getvalue())

    def test_cli_formats_errors(self):
        with patch('dms_test_ledger.cli.load_manifest', side_effect=FileNotFoundError()), redirect_stderr(StringIO()) as output:
            self.assertEqual(1, main(['validate', 'missing.json']))
        self.assertIn('本地文件不存在', output.getvalue())

    def test_doctor_unready_fails_with_repair_action(self):
        with patch('dms_test_ledger.cli._settings'), patch('dms_test_ledger.cli._runtime', return_value=(None, None, None, None)), patch('dms_test_ledger.cli.run_doctor', return_value={'ready': False}), redirect_stdout(StringIO()), redirect_stderr(StringIO()) as output:
            self.assertEqual(1, main(['doctor']))
        self.assertIn('schema plan', output.getvalue())
