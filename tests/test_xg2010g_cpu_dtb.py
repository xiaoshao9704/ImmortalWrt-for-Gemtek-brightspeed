#!/usr/bin/env python3
"""Exercise the CPU artifact check with real compiled DTBs and broken fixtures."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''/dts-v1/;
/ {
    opp-table {
        slow { opp-hz = /bits/ 64 <500000000>; };
        fast { opp-hz = /bits/ 64 <1200000000>; };
    };
    opp-table-cpu-smcc {
        low { opp-level = <0>; };
        high { opp-level = <14>; };
    };
    cpufreq { compatible = "airoha,en7581-cpufreq"; };
    chosen { bootargs = "console=ttyS0,115200 earlycon"; };
};
'''


class CpuDtbTests(unittest.TestCase):
    def check(self, source=SOURCE, corrupt=False):
        with tempfile.TemporaryDirectory() as tmp:
            dtb = Path(tmp) / 'cpu.dtb'
            if corrupt:
                dtb.write_bytes(b'not a device tree')
            else:
                subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(dtb)],
                               input=source, text=True, capture_output=True, check=True)
            return subprocess.run(['python3', str(ROOT / 'scripts/check-xg2010g-cpu-dtb.py'),
                                   str(dtb)], capture_output=True, text=True)

    def test_nominal_table(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('max OPP=1200000000 Hz', result.stdout)

    def test_rejects_higher_frequency_under_arbitrary_name(self):
        for hz in ('1250000000', '1400000000', '1500000000', '5000000000'):
            with self.subTest(hz=hz):
                self.assertNotEqual(self.check(SOURCE.replace('1200000000', hz)).returncode, 0)

    def test_requires_1200_mhz(self):
        self.assertNotEqual(self.check(SOURCE.replace('1200000000', '1150000000')).returncode, 0)

    def test_rejects_overclock_smcc_with_arbitrary_name(self):
        self.assertNotEqual(self.check(SOURCE.replace('opp-level = <14>', 'opp-level = <18>')).returncode, 0)

    def test_rejects_missing_nodes(self):
        for name in ('opp-table', 'opp-table-cpu-smcc', 'cpufreq', 'chosen'):
            with self.subTest(node=name):
                self.assertNotEqual(self.check(SOURCE.replace(name + ' {', 'removed-' + name + ' {')).returncode, 0)

    def test_rejects_corrupt_dtb(self):
        self.assertNotEqual(self.check(corrupt=True).returncode, 0)

    def test_rejects_malformed_frequency(self):
        self.assertNotEqual(self.check(SOURCE.replace('/bits/ 64 <1200000000>', '<1200000000>')).returncode, 0)

    def test_rejects_direct_pll(self):
        self.assertNotEqual(self.check(SOURCE.replace('cpufreq {', 'cpufreq { airoha,force-direct-pll;')).returncode, 0)

    def test_rejects_governor_in_both_boot_arguments(self):
        for name in ('bootargs', 'bootargs-append'):
            with self.subTest(property=name):
                source = SOURCE.replace('bootargs =', name + ' =').replace('earlycon', 'cpufreq.default_governor=powersave')
                self.assertNotEqual(self.check(source).returncode, 0)


if __name__ == '__main__':
    unittest.main()
