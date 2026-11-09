#!/usr/bin/env python3
"""Regression coverage for device-inventory checks across package/ABI changes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / 'scripts/check-installed-package-baseline.py'


class InstalledBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        baseline = {
            'packages': {name: 'old-version' for name in [
                'kernel', 'kmod-iptables', 'kmod-nf-ipt', 'kmod-nf-log6',
                'kmod-nf-log', 'libubus20260925', 'libnghttp2-14', '3proxy']},
            'package_replacements': {'kmod-iptables': 'kmod-nf-ipt',
                                     'kmod-nf-log6': 'kmod-nf-log'},
            'abi_package_symbols': {'libubus20260925': 'libubus',
                                    'libnghttp2-14': 'libnghttp2'},
        }
        (self.root / 'baseline.json').write_text(json.dumps(baseline))
        (self.root / 'metadata').write_text(
            'Package: kmod-nf-ipt\n@@\nPackage: kmod-nf-log\n@@\n'
            'Package: libubus\nABI-Version: 20261028\n@@\n'
            'Package: libnghttp2\nABI-Version: 15\n@@\n'
            'Package: 3proxy\n@@\n')
        (self.root / 'config').write_text(
            'CONFIG_PACKAGE_kmod-nf-ipt=y\nCONFIG_PACKAGE_kmod-nf-log=y\n'
            'CONFIG_PACKAGE_libubus=y\nCONFIG_PACKAGE_libnghttp2=y\n'
            'CONFIG_PACKAGE_3proxy=y\n')
        (self.root / 'manifest').write_text(
            'kernel - 6.18.60-r1\nkmod-nf-ipt - 6.18.60-r1\n'
            'kmod-nf-log - 6.18.60-r1\nlibubus20261028 - new-version\n'
            'libnghttp2-15 - new-version\n3proxy - new-version\n')

    def run_check(self):
        return subprocess.run([
            sys.executable, str(CHECKER), '--config', str(self.root / 'config'),
            '--metadata', str(self.root / 'metadata'),
            '--baseline', str(self.root / 'baseline.json'),
            '--manifest', str(self.root / 'manifest'),
            '--report', str(self.root / 'report.json')], capture_output=True, text=True)

    def test_abi_changes_and_module_consolidation_preserve_baseline(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / 'report.json').read_text())
        self.assertEqual(report['installed_package_count'], 8)
        self.assertEqual(report['required_apk_count'], 6)
        self.assertEqual(report['errors'], [])

    def test_config_missing_device_tool_is_rejected(self):
        path = self.root / 'config'
        path.write_text(path.read_text().replace('CONFIG_PACKAGE_3proxy=y\n', ''))
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CONFIG_PACKAGE_3proxy=y is missing', result.stderr)

    def test_manifest_missing_device_tool_is_rejected(self):
        path = self.root / 'manifest'
        path.write_text(path.read_text().replace('3proxy - new-version\n', ''))
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing installed-baseline package 3proxy', result.stderr)

    def test_stale_abi_in_manifest_is_rejected(self):
        path = self.root / 'manifest'
        path.write_text(path.read_text().replace('libubus20261028', 'libubus20260925'))
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing installed-baseline package libubus20261028', result.stderr)

    def test_removed_package_requires_explicit_migration(self):
        path = self.root / 'metadata'
        path.write_text(path.read_text().replace('Package: 3proxy\n@@\n', ''))
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('package definition 3proxy no longer exists', result.stderr)

    def test_selected_extras_must_also_be_present_in_image(self):
        path = self.root / 'metadata'
        path.write_text(path.read_text() + 'Package: lucky\n@@\n')
        path = self.root / 'config'
        path.write_text(path.read_text() + 'CONFIG_PACKAGE_lucky=y\n')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing selected package lucky', result.stderr)
        path = self.root / 'manifest'
        path.write_text(path.read_text() + 'lucky - new-version\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
