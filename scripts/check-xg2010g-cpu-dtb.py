#!/usr/bin/env python3
"""Validate CPU limits in a compiled XG2010G DTB, failing on unreadable data."""

import argparse
import subprocess
import sys


def check(dtb):
    def read(kind, path, prop):
        result = subprocess.run(['fdtget', '-t', kind, str(dtb), path, prop],
                                capture_output=True, text=True, check=True)
        return result.stdout.split()

    def nodes(path):
        return subprocess.run(['fdtget', '-l', str(dtb), path],
                              capture_output=True, text=True, check=True).stdout.split()

    def props(path):
        return subprocess.run(['fdtget', '-p', str(dtb), path],
                              capture_output=True, text=True, check=True).stdout.split()

    def cells(path, prop, size):
        values = [int(v) for v in read('u', path, prop)]
        if len(values) != size:
            raise ValueError(f'{path}/{prop}: expected {size} cells')
        return values

    frequencies = []
    for node in nodes('/opp-table'):
        high, low = cells('/opp-table/' + node, 'opp-hz', 2)
        hz = (high << 32) | low
        if not 0 < hz <= 1_200_000_000:
            raise ValueError(f'{node}: invalid CPU frequency {hz}')
        frequencies.append(hz)
    if not frequencies or max(frequencies) != 1_200_000_000:
        raise ValueError('CPU OPP table must top out at 1.2 GHz')

    levels = []
    for node in nodes('/opp-table-cpu-smcc'):
        level, = cells('/opp-table-cpu-smcc/' + node, 'opp-level', 1)
        if level > 14:
            raise ValueError(f'{node}: overclock SMCC level {level}')
        levels.append(level)
    if not levels or max(levels) != 14:
        raise ValueError('SMCC OPP table must top out at level 14')

    if 'airoha,force-direct-pll' in props('/cpufreq'):
        raise ValueError('direct PLL opt-in is present')
    for name in props('/chosen'):
        if name in ('bootargs', 'bootargs-append'):
            if any('cpufreq.default_governor=' in arg
                   for arg in read('s', '/chosen', name)):
                raise ValueError('board DTS overrides the cpufreq governor')
    print(f'CPU DTB passed: {dtb}; max OPP=1200000000 Hz, max SMCC=14')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dtb')
    args = parser.parse_args()
    try:
        check(args.dtb)
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f'CPU DTB failed: {error}', file=sys.stderr)
        sys.exit(1)
