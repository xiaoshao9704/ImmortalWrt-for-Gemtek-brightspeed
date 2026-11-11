#!/usr/bin/env python3
"""Run a prepared firewall4 script against host stubs, never a real firewall.

Usage: python3 tests/test_firewall4_load_failure.py --source /path/to/firewall4
Uses bash for pipefail support. This verifies shell control flow, not nft rules.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class LoadFailureTest(unittest.TestCase):
    def run_case(self, action='start', nft_status=0, render_status=0,
                 mutant=False, fallback=False):
        with tempfile.TemporaryDirectory(prefix='fw4-load-test-') as td:
            root = Path(td)
            text = (SOURCE / 'root/sbin/fw4').read_text()
            text = text.replace('LOCK=/var/run/fw4.lock', f'LOCK={root}/lock')
            text = text.replace('STATE=/var/run/fw4.state', f'STATE={root}/state')
            if mutant:
                self.assertIn('nft $VERBOSE -f $STDIN || return 1', text)
                text = text.replace('nft $VERBOSE -f $STDIN || return 1',
                                    'nft $VERBOSE -f $STDIN')
            script = root / 'fw4'
            script.write_text(text)
            scripts = {
                'flock': '#!/bin/sh\nexit 0\n',
                'utpl': '#!/bin/sh\necho "$ACTION" >> "$TRACE"\n'
                        'if [ "$ACTION" = start ]; then\n'
                        ' echo "ruleset stub"; exit "$RENDER_STATUS"\nfi\nexit 0\n',
                'nft': '#!/bin/sh\ncase "$*" in *"-f "*) cat >/dev/null;; esac\n'
                       'echo nft >> "$TRACE"\nexit "$NFT_STATUS"\n',
            }
            for name, contents in scripts.items():
                target = root / name
                target.write_text(contents)
                target.chmod(0o700)
            if action == 'reload':
                (root / 'state').touch()
            env = dict(os.environ, PATH=f'{root}:/usr/bin:/bin', TRACE=str(root / 'trace'),
                       NFT_STATUS=str(nft_status), RENDER_STATUS=str(render_status))
            if fallback:
                cmd = ['bash', '-c', 'bash "$1" "$2" || { echo fallback >> "$TRACE"; exit 42; }',
                       'test', str(script), action]
            else:
                cmd = ['bash', str(script), action]
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
            trace = (root / 'trace').read_text().splitlines()
            return result.returncode, trace

    def test_success_runs_includes(self):
        code, trace = self.run_case()
        self.assertEqual(code, 0)
        self.assertIn('includes', trace)

    def test_start_load_failure(self):
        code, trace = self.run_case(nft_status=7)
        self.assertNotEqual(code, 0)
        self.assertNotIn('includes', trace)

    def test_reload_load_failure(self):
        code, trace = self.run_case(action='reload', nft_status=7)
        self.assertNotEqual(code, 0)
        self.assertNotIn('includes', trace)

    def test_render_failure(self):
        code, trace = self.run_case(render_status=8)
        self.assertNotEqual(code, 0)
        self.assertNotIn('includes', trace)

    def test_failure_reaches_caller_fallback(self):
        code, trace = self.run_case(nft_status=7, fallback=True)
        self.assertEqual(code, 42)
        self.assertIn('fallback', trace)
        self.assertNotIn('includes', trace)

    def test_negative_control_masks_failure(self):
        code, trace = self.run_case(nft_status=7, mutant=True)
        self.assertEqual(code, 0)
        self.assertIn('includes', trace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args, rest = parser.parse_known_args()
    SOURCE = args.source
    unittest.main(argv=[__file__] + rest)
