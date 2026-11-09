#!/usr/bin/env python3
"""Run the phase1 push helper against local Git remotes; gh never contacts GitHub.

python3 tests/test_phase1_push.py --pon-source /path/to/openwrt-pon-drivers
Requires the r71 PON commit and the phase1 firmware commits in the local sources.
Temporary Git bundles are test fixtures; no release package is produced.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--pon-source', type=Path, required=True)
ARGS, REST = PARSER.parse_known_args()
PON_SOURCE = ARGS.pon_source.resolve()
PON_SHA = 'fec6b02eae6ccca8e8313d171102670183224b02'
FORK_SHA = '412f5053ebf0f750d440393f9c1f621d353a2348'
REAL_GIT = shutil.which('git')

GIT_SHIM = '''
import json, os, sys
a = sys.argv[1:]
fault = os.environ['PHASE1_TEST_CASE']
with open(os.environ['PHASE1_TEST_LOG'], 'a') as log:
    log.write(json.dumps(a) + '\\n')
if a[0] == 'ls-remote':
    if fault == 'ls_remote_failure': sys.exit(128)
    if fault == 'missing_branch': sys.exit(0)
    if fault == 'wrong_tip':
        print('0' * 40 + '\\trefs/heads/xg2010g-merged'); sys.exit(0)
if a[:2] == ['fetch', '-q']:
    if fault == 'upstream_fetch_failure' and any('pbs05' in x for x in a): sys.exit(128)
    if fault == 'pon_bundle_failure' and any('pon-drivers.bundle' in x for x in a): sys.exit(128)
    if fault == 'firmware_fetch_failure' and a[2:] == ['origin', 'main']: sys.exit(128)
    if fault == 'firmware_bundle_failure' and any('fork-phase1.bundle' in x for x in a): sys.exit(128)
if fault == 'pon_push_failure' and a == ['push', '-u', 'origin', 'xg2010g-merged']: sys.exit(128)
if fault == 'main_push_failure' and a == ['push', 'origin', 'xg2010g-merged:main']: sys.exit(128)
if fault == 'firmware_push_failure' and a == ['push', '-u', 'origin', 'xg2010g/phase1']: sys.exit(128)
if fault == 'feed_read_failure' and a[0] == 'show': sys.exit(128)
if fault == 'feed_fetch_failure' and a[0] == '-C' and '--depth=1' in a: sys.exit(128)
if fault == 'missing_object' and a[0] == '-C' and 'cat-file' in a: sys.exit(1)
os.execv(os.environ['PHASE1_REAL_GIT'], ['git'] + a)
'''
GH_SHIM = '''
import os, sys
from pathlib import Path
if sys.argv[1:3] == ['repo', 'view']: sys.exit(0)
if sys.argv[1:3] == ['workflow', 'run']:
    Path(os.environ['PHASE1_CI_MARKER']).write_text('attempted')
    sys.exit(1 if os.environ['PHASE1_TEST_CASE'] == 'ci_failure' else 0)
raise SystemExit('Unexpected gh call')
'''


def git(*args):
    return subprocess.run([REAL_GIT, *map(str, args)], check=True,
                          capture_output=True, text=True, timeout=30)


class PushScriptTests(unittest.TestCase):
    def run_case(self, case, expected_exit=1, expected_ci=False, expected_done=False):
        with tempfile.TemporaryDirectory(prefix='phase1-push-') as tmp:
            base = Path(tmp)
            remotes = base / 'remotes'
            pon_remote = remotes / 'xiaoshao9704/openwrt-pon-drivers.git'
            fork_remote = remotes / 'xiaoshao9704/ImmortalWrt-for-Gemtek-brightspeed.git'
            upstream = remotes / 'pbs05/openwrt-pon-drivers.git'
            for source, target in [(PON_SOURCE, pon_remote), (ROOT, fork_remote),
                                   (PON_SOURCE, upstream)]:
                target.parent.mkdir(parents=True, exist_ok=True)
                git('clone', '--shared', '--bare', source, target)
                git('-C', target, 'symbolic-ref', 'HEAD', 'refs/heads/main')
            for repo, ref, sha in [(pon_remote, 'main', 'b7189ea'),
                                   (pon_remote, 'xg2010g-merged', 'b7189ea'),
                                   (fork_remote, 'main', 'd922038f34'),
                                   (fork_remote, 'xg2010g/phase1', '0fce385'),
                                   (upstream, 'main', '2789b97')]:
                git('-C', repo, 'update-ref', 'refs/heads/' + ref, sha)
            # Include the entire required ancestry in local test bundles.
            bundles = base / 'bundles'
            bundles.mkdir()
            for repo, ref, sha, name in [(pon_remote, 'xg2010g-merged', PON_SHA, 'pon-drivers.bundle'),
                                        (fork_remote, 'xg2010g/phase1', FORK_SHA, 'fork-phase1.bundle')]:
                old = git('-C', repo, 'rev-parse', ref).stdout.strip()
                git('-C', repo, 'update-ref', 'refs/heads/' + ref, sha)
                git('-C', repo, 'bundle', 'create', bundles / name, ref, '^' + old)
                git('-C', repo, 'update-ref', 'refs/heads/' + ref, old)
            work = base / 'work'
            if case == 'already_updated':
                for repo, ref, sha in [(pon_remote, 'main', PON_SHA),
                                       (pon_remote, 'xg2010g-merged', PON_SHA),
                                       (fork_remote, 'xg2010g/phase1', FORK_SHA)]:
                    git('-C', repo, 'update-ref', 'refs/heads/' + ref, sha)
            if case == 'cached_bundle_failure':
                case = 'pon_bundle_failure'
                work.mkdir()
                local_pon = work / 'openwrt-pon-drivers'
                git('clone', '--shared', pon_remote, local_pon)
                git('-C', local_pon, 'branch', 'xg2010g-merged', PON_SHA)
            if case == 'missing_bundle':
                (bundles / 'pon-drivers.bundle').unlink()
            bin_dir = base / 'bin'
            bin_dir.mkdir()
            for name, source in [('git', GIT_SHIM), ('gh', GH_SHIM)]:
                path = bin_dir / name
                path.write_text('#!' + sys.executable + '\n' + source)
                path.chmod(0o755)
            marker, log = base / 'ci-attempted', base / 'git.jsonl'
            env = {**os.environ, 'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
                   'WORKDIR': str(work), 'GH_HOST_URL': str(remotes),
                   'BUNDLE_DIR': str(bundles), 'GH_USER': 'xiaoshao9704',
                   'RUN_CI': '0' if case == 'skip_ci' else '1',
                   'PHASE1_TEST_CASE': case, 'PHASE1_TEST_LOG': str(log),
                   'PHASE1_REAL_GIT': REAL_GIT, 'PHASE1_CI_MARKER': str(marker)}
            result = subprocess.run(['sh', str(ROOT / 'scripts/PUSH-phase1.sh')],
                                    env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual((result.returncode, marker.exists(), '完成。' in result.stdout),
                             (expected_exit, expected_ci, expected_done),
                             result.stderr + result.stdout)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            if case in ('upstream_fetch_failure', 'pon_bundle_failure', 'missing_bundle'):
                self.assertFalse(any(call[0] == 'push' for call in calls), calls)
            if case == 'pon_push_failure':
                self.assertNotIn(['push', 'origin', 'xg2010g-merged:main'], calls)
            if expected_exit == 0:
                for repo, ref, sha in [(pon_remote, 'xg2010g-merged', PON_SHA),
                                       (fork_remote, 'xg2010g/phase1', FORK_SHA)]:
                    self.assertEqual(git('-C', repo, 'rev-parse', ref).stdout.strip(), sha)

    def test_first_upgrade(self):
        self.run_case('success', 0, True, True)

    def test_rerun(self):
        self.run_case('already_updated', 0, True, True)

    def test_skip_ci(self):
        self.run_case('skip_ci', 0, False, True)

    def test_optional_main_push(self):
        self.run_case('main_push_failure', 0, True, True)

    def test_ci_failure(self):
        self.run_case('ci_failure', 2, True, False)

    def test_required_failures(self):
        for case in ('upstream_fetch_failure', 'pon_bundle_failure', 'cached_bundle_failure',
                     'pon_push_failure', 'firmware_fetch_failure', 'firmware_bundle_failure',
                     'firmware_push_failure', 'feed_read_failure', 'feed_fetch_failure',
                     'missing_object', 'ls_remote_failure', 'missing_branch', 'wrong_tip',
                     'missing_bundle'):
            with self.subTest(case=case):
                self.run_case(case)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *REST])
