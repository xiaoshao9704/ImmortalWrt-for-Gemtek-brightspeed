#!/usr/bin/env python3
"""Fault-injection tests of the actual patched shell, never the host firewall.

Supply pristine pinned internet-apply and fw4 sources; see the validation doc.
--baseline-ref runs the same assertions against an earlier repository revision.
"""
import argparse
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ONU_PATCH = 'patches/feeds/onu_config/luci-app-onu/100-probe-bridge-nft-fallback.patch'
FW_PATCH = 'package/network/config/firewall4/patches/999-propagate-nft-load-failure.patch'
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--onu-source', type=Path, required=True)
PARSER.add_argument('--fw4-source', type=Path, required=True)
PARSER.add_argument('--baseline-ref')
PARSER.add_argument('--shell', default='dash', help='e.g. dash or "busybox ash"')
ARGS, REST = PARSER.parse_known_args()


def patch_bytes(path):
    if ARGS.baseline_ref:
        proc = subprocess.run(['git', 'show', f'{ARGS.baseline_ref}:{path}'],
                              cwd=ROOT, capture_output=True)
        if proc.returncode and path == FW_PATCH:
            return b''
        proc.check_returncode()
        return proc.stdout
    return (ROOT / path).read_bytes()


def patched(source, target, patch):
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / target
        dest.parent.mkdir(parents=True)
        dest.write_bytes(source.read_bytes())
        dest.chmod(0o755)
        subprocess.run(['git', 'init', '-q', tmp], check=True)
        if patch:
            subprocess.run(['git', 'apply', '--check', '-'], cwd=tmp,
                           input=patch, check=True)
            subprocess.run(['git', 'apply', '-'], cwd=tmp, input=patch, check=True)
        return dest.read_text()


ONU = patched(ARGS.onu_source, 'luci-app-onu/root/usr/libexec/internet-apply',
              patch_bytes(ONU_PATCH))
FW4 = patched(ARGS.fw4_source, 'root/sbin/fw4', patch_bytes(FW_PATCH))
subprocess.run(shlex.split(ARGS.shell) + ['-n'], input=ONU, text=True, check=True)
subprocess.run(['bash', '-n'], input=FW4, text=True, check=True)
# Source production function bodies, suppress only platform bootstrap/main and
# redirect the absolute service invocation. nft/render/install/stamp logic is real.
FUNCTIONS = ONU.split('\nload_internet_config\n')[0]
FUNCTIONS = FUNCTIONS.replace('. /lib/functions.sh', ':')
FUNCTIONS = FUNCTIONS.replace('/etc/init.d/firewall', 'mock_firewall')
PRELUDE = r'''
NFT_FILE="$TEST_DIR/internet.nft"
NFT_LOADED_STAMP="$TEST_DIR/loaded"
NFT_STAGE_DIR="$TEST_DIR"
NFT_REPROBE_LOCK="$TEST_DIR/lock"
ENABLED=1 MODE=bridge PORTS='lan1 lan2' IPOE=1 TRANSMODE=tag UPLINK=pon0
ACTION=reload FULL_OK=1 FILTER_OK=1 RELOAD_OK=1 RELOADS=0 NETWORK_RELOADS=0
logger() { :; }
ubus() { NETWORK_RELOADS=$((NETWORK_RELOADS + 1)); }
check() { "$@" || { echo "ASSERT: $*" >&2; exit 90; }; }
nft() {
    [ "$1" = -c ] || { echo "unexpected nft: $*" >&2; return 99; }
    kind="$(sed -n 's/^# internet-apply bridge ruleset: //p' "$3")"
    printf '%s\n' "$kind" >>"$TEST_DIR/probes"
    case "$kind" in
        full) [ "$FULL_OK" = 1 ];;
        filter) [ "$FILTER_OK" = 1 ];;
        inactive) return 0;;
        *) return 1;;
    esac
}
mock_firewall() {
    check test "$1" = reload
    RELOADS=$((RELOADS + 1))
    [ "$RELOAD_OK" = 1 ] || return 1
    cp "$NFT_FILE" "$TEST_DIR/kernel-model"
}
seed() {
    render_bridge_rules "$NFT_FILE" "$1"
    NFT_RULESET="$1"
}
live() { check cmp -s "$NFT_FILE" "$TEST_DIR/kernel-model"; check nft_loaded_is "$1"; }
no_stamp() { check test ! -e "$NFT_LOADED_STAMP"; }
'''


class OnuStateTests(unittest.TestCase):
    def run_script(self, directory, body):
        return subprocess.run(shlex.split(ARGS.shell), input=FUNCTIONS + PRELUDE + body,
                              text=True, capture_output=True,
                              env={**os.environ, 'TEST_DIR': str(directory)}, timeout=10)

    def run_case(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(tmp, body)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_boot_filter_then_ifup(self):
        self.run_case('''
FULL_OK=0 ACTION=boot
write_nft_rules; reload_runtime
check nft_file_is filter; no_stamp; check test "$RELOADS" = 0
ACTION=reprobe; reprobe_bridge_nft
check test "$RELOADS" = 1; live filter
reprobe_bridge_nft; check test "$RELOADS" = 1
check test "$NETWORK_RELOADS" = 0
''')

    def test_boot_full_then_ifup(self):
        self.run_case('''
ACTION=boot; write_nft_rules; reload_runtime; no_stamp
ACTION=reprobe; reprobe_bridge_nft; live full
check test "$RELOADS" = 1
reprobe_bridge_nft; check test "$RELOADS" = 1
''')

    def test_existing_filter_failed_reload_retries(self):
        self.run_case('''
seed filter; FULL_OK=0 RELOAD_OK=0
reprobe_bridge_nft; check test "$RELOADS" = 1; no_stamp
RELOAD_OK=1; reprobe_bridge_nft; live filter
check test "$RELOADS" = 2
''')

    def test_existing_filter_commit_helper_reloads(self):
        self.run_case('''
seed filter; FULL_OK=0
tmp="$(stage_nft_file)"; render_bridge_rules "$tmp" filter
commit_probed_rules filter "$tmp"
check test "$RELOADS" = 1; live filter
''')

    def test_boot_firewall_already_started_still_needs_acknowledgement(self):
        self.run_case('''
FULL_OK=0 ACTION=boot
write_nft_rules; reload_runtime
# Model the separate START=19 firewall start, which does not write our stamp.
cp "$NFT_FILE" "$TEST_DIR/kernel-model"; no_stamp
ACTION=reprobe; reprobe_bridge_nft
check test "$RELOADS" = 1; live filter
''')

    def test_interrupted_reload_does_not_leave_old_stamp(self):
        self.run_case('''
seed full; reload_runtime; live full
mock_firewall() { exit 23; }
(reload_runtime); check test "$?" = 23
no_stamp
''')

    def test_downgrade_failure_then_ifup(self):
        self.run_case('''
seed full; reload_runtime; live full
FULL_OK=0 RELOAD_OK=0; reprobe_bridge_nft
check nft_file_is filter; no_stamp
check test "$RELOADS" = 2
RELOAD_OK=1; reprobe_bridge_nft; live filter
check test "$RELOADS" = 3
''')

    def test_upgrade_failure_then_ifup(self):
        self.run_case('''
seed filter; reload_runtime
RELOAD_OK=0; reprobe_bridge_nft
check nft_file_is full; no_stamp
RELOAD_OK=1; reprobe_bridge_nft; live full
check test "$RELOADS" = 3
''')

    def test_failed_round_trip_cannot_reuse_old_full_stamp(self):
        self.run_case('''
seed full; reprobe_bridge_nft; live full
FULL_OK=0 RELOAD_OK=0; reprobe_bridge_nft
FULL_OK=1; reprobe_bridge_nft
no_stamp; check test "$RELOADS" = 3
RELOAD_OK=1; reprobe_bridge_nft; live full
check test "$RELOADS" = 4
''')

    def test_legacy_kind_only_stamp_is_not_trusted(self):
        self.run_case('''
seed filter; FULL_OK=0
printf 'filter\n' >"$NFT_LOADED_STAMP"
reprobe_bridge_nft; live filter; check test "$RELOADS" = 1
''')

    def test_apply_reload_failure_then_ifup(self):
        self.run_case('''
FULL_OK=0; write_nft_rules; reload_runtime; live filter
IPOE=0; write_nft_rules
RELOAD_OK=0; (reload_runtime); check test "$?" != 0
no_stamp
RELOAD_OK=1; reprobe_bridge_nft; live filter
''')

    def test_apply_aborts_after_replacement(self):
        for mode in ('full', 'filter'):
            with self.subTest(mode=mode):
                self.run_case(f'''
FULL_OK={'1' if mode == 'full' else '0'}
write_nft_rules; reload_runtime; live {mode}
IPOE=0; write_nft_rules
# Simulate a later UCI/config failure: do not call reload_runtime.
no_stamp
reprobe_bridge_nft; live {mode}; check test "$RELOADS" = 2
''')

    def test_same_kind_file_change_invalidates_stamp(self):
        self.run_case('''
seed full; reload_runtime
IPOE=0; render_bridge_rules "$NFT_FILE" full
if nft_loaded_is full; then exit 91; fi
reprobe_bridge_nft; live full; check test "$RELOADS" = 2
''')

    def test_mv_failure_does_not_reload_or_stamp_target(self):
        self.run_case('''
seed filter; reload_runtime
mv() { return 1; }
reprobe_bridge_nft
check nft_file_is filter; check test "$RELOADS" = 1
if nft_loaded_is full; then exit 91; fi
unset -f mv
reprobe_bridge_nft; live full; check test "$RELOADS" = 2
''')

    def test_apply_install_failure_is_fatal(self):
        for mode in ('full', 'filter', 'inactive'):
            with self.subTest(mode=mode):
                self.run_case(f'''
seed filter; cp "$NFT_FILE" "$TEST_DIR/old"
FULL_OK={'0' if mode == 'filter' else '1'}
ENABLED={'0' if mode == 'inactive' else '1'}
mv() {{ return 1; }}
(write_nft_rules); check test "$?" != 0
check cmp -s "$NFT_FILE" "$TEST_DIR/old"
check test "$RELOADS" = 0; no_stamp
''')

    def test_chmod_failure_does_not_install(self):
        self.run_case('''
seed filter; cp "$NFT_FILE" "$TEST_DIR/old"
chmod() { return 1; }
reprobe_bridge_nft
check cmp -s "$NFT_FILE" "$TEST_DIR/old"
check test "$RELOADS" = 0; no_stamp
''')

    def test_rejected_probes_preserve_disk_and_kernel(self):
        self.run_case('''
seed full; reload_runtime; cp "$NFT_FILE" "$TEST_DIR/old"
FULL_OK=0 FILTER_OK=0; reprobe_bridge_nft
check cmp -s "$NFT_FILE" "$TEST_DIR/old"; live full
check test "$RELOADS" = 1
(write_nft_rules); check test "$?" != 0
check cmp -s "$NFT_FILE" "$TEST_DIR/old"; live full
''')

    def test_empty_staging_cannot_replace_rules(self):
        self.run_case('''
seed filter; cp "$NFT_FILE" "$TEST_DIR/old"
tmp="$(stage_nft_file)"; commit_probed_rules full "$tmp"
check cmp -s "$NFT_FILE" "$TEST_DIR/old"
check test "$RELOADS" = 0; no_stamp
''')

    def test_disabled_routed_empty_ports_skip_reprobe(self):
        for setup in ('ENABLED=0', 'MODE=dhcp', "PORTS=''"):
            with self.subTest(setup=setup):
                self.run_case(setup + '''
reprobe_bridge_nft; check test ! -f "$NFT_FILE"
check test "$RELOADS" = 0; no_stamp
''')

    def test_probe_order_and_filter_contents(self):
        self.run_case('''
FULL_OK=0; write_nft_rules
check test "$(cat "$TEST_DIR/probes")" = "$(printf 'full\\nfilter')"
check grep -q '0x8863, 0x8864' "$NFT_FILE"
check grep -q 'arp, ip, ip6' "$NFT_FILE"
check grep -q 'priority filter - 1' "$NFT_FILE"
check test "$(grep -Ec '^[[:space:]]*(flowtable|ct zone set|flow offload)' "$NFT_FILE")" = 0
''')

    def test_untag_full_uses_raw_uplink(self):
        self.run_case('''
TRANSMODE=untag; write_nft_rules
check nft_file_is full
check grep -q 'devices = { "pon0", "lan1", "lan2" }' "$NFT_FILE"
check grep -q 'ct zone set 1' "$NFT_FILE"
check grep -q 'flags offload' "$NFT_FILE"
''')

    def test_stamp_write_failure_is_not_success(self):
        self.run_case('''
seed full
nft_mark_loaded() { return 1; }
(reload_runtime); check test "$?" != 0
no_stamp
''')

    def test_stamp_copy_is_not_visible_until_complete(self):
        self.run_case('''
seed full
cp() {
    if [ "$2" != "$TEST_DIR/kernel-model" ]; then
        head -c 20 "$1" >"$2"
        no_stamp
    fi
    command cp "$@"
}
reload_runtime; live full
''')

    def test_stamp_io_failure_cleans_staging_and_retries(self):
        for operation in ('mktemp', 'cp', 'mv'):
            with self.subTest(operation=operation):
                self.run_case('''
seed full
''' + {
                    'mktemp': '''mktemp() { return 1; }''',
                    'cp': '''cp() {
    if [ "$2" != "$TEST_DIR/kernel-model" ]; then
        head -c 20 "$1" >"$2"
        return 1
    fi
    command cp "$@"
}''',
                    'mv': '''mv() { return 1; }''',
                }[operation] + f'''
(reload_runtime); check test "$?" != 0
no_stamp
for leftover in "$NFT_LOADED_STAMP".*; do check test ! -e "$leftover"; done
unset -f {operation}
reprobe_bridge_nft; live full; check test "$RELOADS" = 1
''')

    def test_sigkill_during_stamp_copy_never_publishes_partial_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_script(tmp, '''
seed full
cp() {
    if [ "$2" != "$TEST_DIR/kernel-model" ]; then
        head -c 20 "$1" >"$2"
        kill -KILL "$$"
    fi
    command cp "$@"
}
reload_runtime
''')
            self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr)
            self.assertFalse((Path(tmp) / 'loaded').exists())
            # SIGKILL cannot run cleanup. A unique orphan is harmless and is
            # never considered a success stamp by the next invocation.
            orphans = list(Path(tmp).glob('loaded.*'))
            self.assertEqual(len(orphans), 1)
            self.assertEqual(orphans[0].stat().st_size, 20)
            retry = self.run_script(tmp, 'reprobe_bridge_nft; live full\n')
            self.assertEqual(retry.returncode, 0, retry.stdout + retry.stderr)


class FirewallExitTests(unittest.TestCase):
    def run_fw4(self, command, nft_rc, render_rc, includes_rc=0):
        # bash supports fw4's pipefail and fd 1000. No real nft/ubus calls.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            fw = FW4.replace('LOCK=/var/run/fw4.lock', f'LOCK={tmp}/lock')
            fw = fw.replace('STATE=/var/run/fw4.state', f'STATE={tmp}/state')
            (d / 'fw4').write_text(fw)
            (d / 'state').touch()
            (d / 'utpl').write_text('''#!/bin/sh
printf '%s\\n' "$ACTION" >>"$TEST_DIR/actions"
if [ "$ACTION" != includes ]; then
    printf 'table inet fw4 {}\\n'
    exit "$RENDER_RC"
fi
exit "$INCLUDES_RC"
''')
            (d / 'nft').write_text('#!/bin/sh\ncat >/dev/null\nexit "$NFT_RC"\n')
            for name in ('nft', 'utpl'):
                (d / name).chmod(0o755)
            env = {**os.environ, 'PATH': tmp + ':' + os.environ['PATH'],
                   'TEST_DIR': tmp, 'NFT_RC': str(nft_rc),
                   'RENDER_RC': str(render_rc), 'INCLUDES_RC': str(includes_rc)}
            proc = subprocess.run(['bash', str(d / 'fw4'), command], env=env,
                                  capture_output=True, timeout=10)
            return proc, (d / 'actions').read_text().splitlines()

    def test_real_fw4_start_pipeline_status(self):
        for nft_rc, render_rc, includes_rc in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
            with self.subTest(nft=nft_rc, render=render_rc, includes=includes_rc):
                proc, actions = self.run_fw4('reload', nft_rc, render_rc, includes_rc)
                self.assertEqual(proc.returncode == 0,
                                 not (nft_rc or render_rc or includes_rc))
                if nft_rc or render_rc:
                    self.assertNotIn('includes', actions)

    def test_reload_sets_already_propagates_pipeline_status(self):
        # R5-N2 is not a defect: no subsequent command overwrites the status.
        for nft_rc, render_rc in ((0, 0), (7, 0), (0, 9), (7, 9)):
            with self.subTest(nft=nft_rc, render=render_rc):
                proc, actions = self.run_fw4('reload-sets', nft_rc, render_rc)
                self.assertEqual(proc.returncode, nft_rc or render_rc)
                self.assertEqual(actions, ['reload-sets'])


if __name__ == '__main__':
    unittest.main(argv=[__file__, *REST], verbosity=2)
