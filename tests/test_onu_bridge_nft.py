#!/usr/bin/env python3
"""Fault-injection tests of the actual patched shell, never the host firewall.

Supply pristine pinned internet-apply and fw4 sources; see the validation doc.
--baseline-ref runs the same assertions against an earlier repository revision.
"""
import argparse
import os
from pathlib import Path
import re
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


def patched(source, target, patch, read_target=None):
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
        return (Path(tmp) / (read_target or target)).read_text()


ONU = patched(ARGS.onu_source, 'luci-app-onu/root/usr/libexec/internet-apply',
              patch_bytes(ONU_PATCH))
FW4 = patched(ARGS.fw4_source, 'root/sbin/fw4', patch_bytes(FW_PATCH))
HOTPLUG = patched(ARGS.onu_source, 'luci-app-onu/root/usr/libexec/internet-apply',
                  patch_bytes(ONU_PATCH),
                  'luci-app-onu/root/etc/hotplug.d/iface/99-internet-bridge-nft')
subprocess.run(shlex.split(ARGS.shell) + ['-n'], input=ONU, text=True, check=True)
subprocess.run(['bash', '-n'], input=FW4, text=True, check=True)
# Source production function bodies, suppress only platform bootstrap/main and
# redirect the absolute service invocation. nft/render/install/stamp logic is real.
FUNCTIONS = ONU.split('\nload_internet_config\n')[0]
FUNCTIONS = FUNCTIONS.replace('. /lib/functions.sh', ':')
FUNCTIONS = FUNCTIONS.replace('/etc/init.d/firewall', 'mock_firewall')
MAIN = '\nload_internet_config\n' + ONU.split('\nload_internet_config\n', 1)[1]
PRELUDE = r'''
NFT_FILE="$TEST_DIR/internet.nft"
NFT_LOADED_STAMP="$TEST_DIR/loaded"
NFT_STAGE_DIR="$TEST_DIR"
NFT_REPROBE_LOCK="$TEST_DIR/lock"
INTERNET_STATUS_FILE="$TEST_DIR/status"
OFFLOAD_BACKUP="$TEST_DIR/offload.orig"
ENABLED=1 MODE=bridge PORTS='lan1 lan2' IPOE=1 TRANSMODE=tag UPLINK=pon0
ACTION=reload FULL_OK=1 FILTER_OK=1 RELOAD_OK=1 RELOADS=0 NETWORK_RELOADS=0
logger() { printf '%s\n' "$*" >>"$TEST_DIR/log"; }
ubus() {
    check test "$*" = 'call network reload'
    NETWORK_RELOADS=$((NETWORK_RELOADS + 1))
    printf 'network-reload\n' >>"$TEST_DIR/events"
}
check() { "$@" || { echo "ASSERT: $*" >&2; exit 90; }; }
nft() {
    if [ "$*" = 'list tables' ]; then
        printf 'table inet fw4\n'
        [ ! -f "$TEST_DIR/kernel-wanup" ] || printf 'table bridge wanup\n'
        return 0
    fi
    if [ "$*" = 'delete table bridge wanup' ]; then
        printf 'delete-wanup\n' >>"$TEST_DIR/events"
        [ "${DELETE_OK:-1}" = 1 ] || return 1
        rm -f "$TEST_DIR/kernel-wanup"
        return 0
    fi
    [ "$1" = -c ] || { echo "unexpected nft: $*" >&2; return 99; }
    kind="$(sed -n 's/^# internet-apply bridge ruleset: //p' "$3")"
    printf '%s\n' "$kind" >>"$TEST_DIR/probes"
    case "$kind" in
        full) [ "$FULL_OK" = 1 ] || { echo 'mock full rejected' >&2; return 1; };;
        filter) [ "$FILTER_OK" = 1 ] || { echo 'mock filter rejected' >&2; return 1; };;
        inactive|unfiltered) return 0;;
        *) return 1;;
    esac
}
mock_firewall() {
    check test "$1" = reload
    RELOADS=$((RELOADS + 1))
    printf 'firewall-reload\n' >>"$TEST_DIR/events"
    [ "$RELOAD_OK" = 1 ] || return 1
    cp "$NFT_FILE" "$TEST_DIR/kernel-model"
    case "$(head -1 "$NFT_FILE")" in
        *': full'|*': filter') cat "$NFT_FILE" >"$TEST_DIR/kernel-wanup";;
    esac
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
# The unchanged UNTAG policy still rejects both failures. TAG now has an
# explicitly permitted transparent fallback, covered by the pipeline tests.
TRANSMODE=untag
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


PIPELINE_SETUP = r'''
ACTION="${1:-reload}"
FULL_OK="${TEST_FULL_OK:-1}" FILTER_OK="${TEST_FILTER_OK:-1}"
TRANSMODE="${TEST_TRANSMODE:-tag}" DELETE_OK="${TEST_DELETE_OK:-1}"
VLAN=100 OFFLOAD=1 IP_VERSION=ipv4
# Platform discovery/config input is stubbed; the production main, UCI writers,
# nft staging, firewall/stamp and hotplug paths all execute below.
load_internet_config() { :; }
config_load() { :; }
config_foreach() { :; }
validate_config() { :; }
uci() {
    printf '%s\n' "$*" >>"$TEST_DIR/uci"
    case "$*" in
        '-q get '*|'-q show '*) return 1;;
        'commit onu-internet') printf 'reload\n' >>"$TEST_DIR/procd-reloads";;
    esac
    return 0
}
ubus() {
    check test "$*" = 'call network reload'
    printf 'network-reload\n' >>"$TEST_DIR/events"
    printf 'bridge\n' >"$TEST_DIR/runtime-mode"
}
'''


class TagPipelineTests(unittest.TestCase):
    functions = FUNCTIONS

    def prepare(self, directory, old_bridge=False):
        directory = Path(directory)
        (directory / 'runtime-mode').write_text('pppoe\n')
        if old_bridge:
            old = '# internet-apply bridge ruleset: full\n# old ports\n'
            for name in ('internet.nft', 'loaded', 'kernel-model', 'kernel-wanup'):
                (directory / name).write_text(old)
        else:
            (directory / 'internet.nft').write_text('# old routing configuration\n')

    def invoke(self, directory, action='reload', full=1, filtering=1,
               transmode='tag', delete=1, status_path=None, event='ifup'):
        directory = Path(directory)
        runner = directory / 'apply'
        text = '#!/bin/sh\n' + self.functions + PRELUDE + PIPELINE_SETUP
        if status_path:
            text += '\nINTERNET_STATUS_FILE=' + shlex.quote(str(status_path)) + '\n'
        text += MAIN
        runner.write_text(text)
        runner.chmod(0o755)
        syntax = subprocess.run(shlex.split(ARGS.shell) + ['-n', str(runner)],
                                capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        env = {**os.environ, 'TEST_DIR': str(directory), 'TEST_FULL_OK': str(full),
               'TEST_FILTER_OK': str(filtering), 'TEST_TRANSMODE': transmode,
               'TEST_DELETE_OK': str(delete)}
        if action == 'hotplug':
            hotplug = directory / 'hotplug'
            hotplug.write_text(HOTPLUG.replace('/usr/libexec/internet-apply',
                shlex.join(shlex.split(ARGS.shell) + [str(runner)])))
            env.update(ACTION=event, INTERFACE='wan')
            cmd = shlex.split(ARGS.shell) + [str(hotplug)]
        else:
            cmd = shlex.split(ARGS.shell) + [str(runner), action]
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def events(self, directory):
        path = Path(directory) / 'events'
        return path.read_text().splitlines() if path.exists() else []

    def status(self, directory):
        path = Path(directory) / 'status'
        self.assertTrue(path.exists(), 'last TAG result must be readable')
        return dict(line.split('=', 1) for line in path.read_text().splitlines())

    def matching_stamp(self, directory):
        d = Path(directory)
        self.assertTrue((d / 'loaded').exists(), 'successful reload must publish a stamp')
        self.assertEqual((d / 'loaded').read_bytes(), (d / 'internet.nft').read_bytes())

    def no_config_reload_loop(self, directory):
        commands = (Path(directory) / 'uci').read_text().splitlines()
        self.assertFalse(any(re.match(r'(set|delete|rename|commit) onu-internet', c)
                             for c in commands), commands)
        self.assertFalse((Path(directory) / 'procd-reloads').exists())

    def test_tag_both_rejected_applies_transparent_bridge_and_removes_old_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d, old_bridge=True)
            self.success(self.invoke(d, full=0, filtering=0))
            self.assertEqual((d / 'runtime-mode').read_text(), 'bridge\n')
            rules = (d / 'internet.nft').read_text()
            self.assertEqual(rules.splitlines()[0], '# internet-apply bridge ruleset: unfiltered')
            self.assertFalse(any(line.strip() and not line.startswith('#')
                                 for line in rules.splitlines()))
            self.assertFalse((d / 'kernel-wanup').exists(), 'old restrictions must be gone')
            self.matching_stamp(d)
            status = self.status(d)
            self.assertEqual(status['ruleset'], 'unfiltered')
            self.assertEqual(status['phase'], 'applied')
            self.assertEqual(status['warning'], 'bridge_rules_rejected')
            self.assertIn('mock filter rejected', status['nft_error'])
            self.assertIn('Both ONU bridge rulesets rejected', (d / 'log').read_text())
            commands = (d / 'uci').read_text()
            for command in ('set network.luci_wanup_dev.type=8021q',
                            'set network.luci_wanup_dev.vid=100',
                            'add_list network.luci_wanup_bridge.ports=ct-wanup',
                            'set network.wan.device=br-wanup'):
                self.assertIn(command, commands)
            self.assertLess(self.events(d).index('delete-wanup'),
                            self.events(d).index('network-reload'))
            self.no_config_reload_loop(d)

    def test_tag_both_rejected_without_previous_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            self.success(self.invoke(d, full=0, filtering=0))
            self.assertEqual((d / 'runtime-mode').read_text(), 'bridge\n')
            self.assertNotIn('delete-wanup', self.events(d))
            self.assertEqual(self.status(d)['ruleset'], 'unfiltered')

    def test_first_full_apply_then_hotplug_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            self.success(self.invoke(d))
            self.assertEqual((d / 'internet.nft').read_text().splitlines()[0],
                             '# internet-apply bridge ruleset: full')
            self.matching_stamp(d)
            for _ in range(3):
                self.success(self.invoke(d, action='hotplug'))
            self.assertEqual(self.events(d).count('firewall-reload'), 1)
            self.assertEqual(self.events(d).count('network-reload'), 1)
            self.assertEqual(self.status(d)['warning'], 'none')
            self.no_config_reload_loop(d)

    def test_boot_filter_then_wan_full_upgrade_reloads_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            self.success(self.invoke(d, action='boot', full=0))
            self.assertEqual((d / 'internet.nft').read_text().splitlines()[0],
                             '# internet-apply bridge ruleset: filter')
            self.assertFalse((d / 'loaded').exists())
            self.assertEqual(self.status(d)['phase'], 'staged')
            # Model the separate START=19 firewall start, without our stamp.
            for name in ('kernel-model', 'kernel-wanup'):
                (d / name).write_bytes((d / 'internet.nft').read_bytes())
            self.success(self.invoke(d, action='hotplug', full=1))
            self.assertEqual((d / 'internet.nft').read_text().splitlines()[0],
                             '# internet-apply bridge ruleset: full')
            self.matching_stamp(d)
            for _ in range(3):
                self.success(self.invoke(d, action='hotplug'))
            self.assertEqual(self.events(d).count('firewall-reload'), 1)
            self.assertNotIn('network-reload', self.events(d))
            self.no_config_reload_loop(d)

    def test_boot_both_rejected_stages_transparent_bridge_without_false_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            (d / 'runtime-mode').write_text('not-started\n')
            self.success(self.invoke(d, action='boot', full=0, filtering=0))
            self.assertEqual((d / 'internet.nft').read_text().splitlines()[0],
                             '# internet-apply bridge ruleset: unfiltered')
            self.assertEqual(self.status(d)['phase'], 'staged')
            self.assertIn('set network.wan.device=br-wanup', (d / 'uci').read_text())
            self.assertFalse((d / 'loaded').exists())
            self.assertEqual(self.events(d), [])
            # Separate firewall/network starts, then the real wan ifup hook.
            (d / 'kernel-model').write_bytes((d / 'internet.nft').read_bytes())
            (d / 'runtime-mode').write_text('bridge\n')
            for _ in range(3):
                self.success(self.invoke(d, action='hotplug', full=0, filtering=0))
            self.matching_stamp(d)
            self.assertEqual(self.status(d)['phase'], 'loaded')
            self.assertEqual(self.events(d).count('firewall-reload'), 1)
            self.assertNotIn('network-reload', self.events(d))
            self.no_config_reload_loop(d)

    def test_unfiltered_reprobe_recovers_full_and_updates_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            self.success(self.invoke(d, full=0, filtering=0))
            self.success(self.invoke(d, action='hotplug', full=0, filtering=0))
            self.assertEqual(self.events(d).count('firewall-reload'), 1)
            self.success(self.invoke(d, action='hotplug'))
            self.assertEqual((d / 'internet.nft').read_text().splitlines()[0],
                             '# internet-apply bridge ruleset: full')
            self.assertEqual(self.status(d)['warning'], 'none')
            self.assertEqual(self.status(d)['phase'], 'loaded')
            self.assertEqual(self.events(d).count('firewall-reload'), 2)
            self.success(self.invoke(d, action='hotplug'))
            self.assertEqual(self.events(d).count('firewall-reload'), 2)
            self.assertEqual(self.events(d).count('network-reload'), 1)

    def test_old_table_delete_failure_does_not_acknowledge_or_reload_network(self):
        for action in ('reload', 'hotplug'):
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                self.prepare(d, old_bridge=True)
                result = self.invoke(d, action=action, full=0, filtering=0, delete=0)
                if action == 'reload':
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0)  # Do not abort later hotplug scripts.
                self.assertTrue((d / 'kernel-wanup').exists())
                self.assertFalse((d / 'loaded').exists())
                self.assertNotIn('network-reload', self.events(d))
                self.assertEqual(self.status(d)['phase'], 'load_failed')

    def test_status_io_error_is_logged_without_breaking_tag_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            self.success(self.invoke(d, full=0, filtering=0,
                                     status_path=d / 'missing/status'))
            self.assertIn('Cannot create internet apply status file', (d / 'log').read_text())
            self.assertEqual((d / 'runtime-mode').read_text(), 'bridge\n')

    def test_untag_both_rejected_keeps_original_failure_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.prepare(d)
            old = (d / 'internet.nft').read_bytes()
            result = self.invoke(d, full=0, filtering=0, transmode='untag')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((d / 'internet.nft').read_bytes(), old)
            self.assertEqual((d / 'runtime-mode').read_text(), 'pppoe\n')
            self.assertEqual(self.events(d), [])

    def test_negative_controls_reject_regressions(self):
        def replace_once(source, old, new):
            self.assertEqual(source.count(old), 1, old)
            return source.replace(old, new, 1)

        def body(name, replacement):
            def mutate(source):
                text, count = re.subn(r'^' + re.escape(name) + r'\(\) \{\n.*?^\}',
                                      name + '() {\n' + replacement + '\n}',
                                      source, flags=re.M | re.S)
                self.assertEqual(count, 1, name)
                return text
            return mutate

        def inject(name, code):
            return lambda source: replace_once(source, name + '() {\n',
                                                name + '() {\n' + code + '\n')

        def suppress_upgrade(source):
            before, after = source.split('reprobe_bridge_nft() {', 1)
            return before + 'reprobe_bridge_nft() {' + replace_once(
                after, 'if stage_validated_rules "$tmp" full; then', 'if false; then')

        transparent = 'test_tag_both_rejected_applies_transparent_bridge_and_removes_old_table'
        full = 'test_first_full_apply_then_hotplug_is_idempotent'
        cases = [
            ('reject transparent fallback', body('tag_unfiltered_rules', '\treturn 1'), transparent),
            ('omit bridge topology', body('write_network_config', '\treturn 0'), transparent),
            ('retain old restrictions', body('remove_unfiltered_wanup_table', '\treturn 0'), transparent),
            ('lose readable status', body('report_bridge_status', '\treturn 0'), transparent),
            ('lose warning log', body('warn', '\t:'), transparent),
            ('write procd trigger source', inject('report_bridge_status',
                '\tuci set onu-internet.config.mode=bridge\n\tuci commit onu-internet'), transparent),
            ('omit reload acknowledgement', body('nft_mark_loaded', '\treturn 0'), full),
            ('do not upgrade after ifup', suppress_upgrade,
                'test_boot_filter_then_wan_full_upgrade_reloads_only_once'),
            ('forget loaded stamp on every ifup', body('nft_loaded_is', '\treturn 1'), full),
            ('mislabel full rules', lambda s: replace_once(s,
                '# internet-apply bridge ruleset: full\n',
                '# internet-apply bridge ruleset: filter\n'), full),
            ('leave stale warning', inject('report_bridge_status',
                '\t[ "$1" != full ] || return 0'),
                'test_unfiltered_reprobe_recovers_full_and_updates_warning'),
            ('ignore failed table removal', lambda s: replace_once(s,
                'nft delete table bridge wanup || return 1',
                'nft delete table bridge wanup || true'),
                'test_old_table_delete_failure_does_not_acknowledge_or_reload_network'),
            ('reload netifd from ifup', inject('reprobe_bridge_nft',
                '\tubus call network reload >/dev/null'), full),
            ('change UNTAG policy too', lambda s: replace_once(s,
                '[ "$TRANSMODE" = \'tag\' ] || return 1', ':'),
                'test_untag_both_rejected_keeps_original_failure_policy'),
            ('make status I/O fatal', lambda s: replace_once(s,
                'warn "Cannot create internet apply status file $file"\n\t\treturn 0',
                'fail "Cannot create internet apply status file $file"'),
                'test_status_io_error_is_logged_without_breaking_tag_bridge'),
            ('mark boot rules loaded without reload', lambda s: replace_once(s,
                '[ "$ACTION" = \'boot\' ] && return 0',
                '[ "$ACTION" != \'boot\' ] || { nft_mark_loaded "$NFT_RULESET"; return 0; }'),
                'test_boot_both_rejected_stages_transparent_bridge_without_false_stamp'),
        ]
        original = self.functions
        try:
            for label, mutate, test in cases:
                with self.subTest(regression=label):
                    self.functions = mutate(original)
                    syntax = subprocess.run(shlex.split(ARGS.shell) + ['-n'],
                        input=self.functions + PRELUDE + PIPELINE_SETUP + MAIN,
                        text=True, capture_output=True)
                    self.assertEqual(syntax.returncode, 0, syntax.stderr)
                    with self.assertRaises(AssertionError, msg=label):
                        getattr(self, test)()
        finally:
            self.functions = original


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
