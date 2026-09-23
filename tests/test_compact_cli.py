import subprocess
import sys
import unittest


class CompactCliTests(unittest.TestCase):
    def test_legacy_paths_fail_before_network_or_file_reads(self):
        for args in [('automate', '--sheets'), ('automate', '--publish-sheets'),
                     ('sync',), ('import-journal', '--journal', 'absent.xlsx')]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-m', 'pepper', *args],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('Legacy journal integration retired', result.stderr)

    def test_compact_publish_requires_compact_read(self):
        result = subprocess.run([sys.executable, '-m', 'pepper', 'automate',
                                 '--publish-research-sheets'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires --research-sheets', result.stderr)
