from pathlib import Path
import subprocess
import sys
import unittest


class BundledRuntimeTests(unittest.TestCase):
    def test_bundle_propagates_success_and_failure_exit_codes(self):
        root = Path(__file__).resolve().parents[1]
        runtime = root / 'skill/lark-test-ledger/scripts/lark-test-ledger.pyz'
        for arguments, expected in [(['--help'], 0), (['validate', str(root / 'missing-manifest.json')], 1)]:
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, str(runtime), *arguments], capture_output=True, encoding='utf-8')
                self.assertEqual(expected, result.returncode, result.stderr)
                if expected:
                    self.assertIn('用例文件校验失败', result.stderr)
