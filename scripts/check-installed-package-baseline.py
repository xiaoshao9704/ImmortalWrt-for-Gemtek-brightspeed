#!/usr/bin/env python3
"""Check selected packages and image manifests against the running XG2010G."""
import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]


def metadata(path):
    packages = {}
    current = None
    for line in path.read_text().splitlines():
        if line.startswith('Package: '):
            current = {}
            packages[line.removeprefix('Package: ')] = current
        elif line == '@@':
            current = None
        elif current is not None and line.startswith('ABI-Version: '):
            current['abi'] = line.removeprefix('ABI-Version: ')
    return packages


def apk_name(name, packages):
    # Match include/feeds.mk FormatABISuffix, including digit-ending names.
    abi = packages[name].get('abi', '')
    if name.startswith('kmod-') or not abi:
        return name
    return name + ('-' if name[-1].isdigit() else '') + abi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, default=ROOT / 'tmp/.packageinfo')
    parser.add_argument('--baseline', type=Path,
                        default=ROOT / 'docs/xg2010g-installed-baseline.json')
    parser.add_argument('--manifest', type=Path, action='append', default=[])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    packages = metadata(args.metadata)
    selected = set(re.findall(r'^CONFIG_PACKAGE_(.+)=y$', args.config.read_text(), re.M))
    aliases = {**baseline.get('abi_package_symbols', {}),
               **baseline.get('package_replacements', {})}
    required = set()
    errors = []
    mapping = {}
    for installed in baseline['packages']:
        symbol = aliases.get(installed, installed)
        if symbol == 'kernel':
            expected = 'kernel'  # Added by image construction, not a menu option.
        elif symbol not in packages:
            errors.append(f'{installed}: package definition {symbol} no longer exists')
            continue
        else:
            expected = apk_name(symbol, packages)
            if symbol not in selected:
                errors.append(f'{installed}: CONFIG_PACKAGE_{symbol}=y is missing')
        required.add(expected)
        mapping[installed] = {'config_package': symbol, 'expected_apk_name': expected}

    predicted = {apk_name(name, packages) for name in selected & packages.keys()} | {'kernel'}
    manifests = {}
    for path in args.manifest:
        actual = set()
        for line in path.read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            match = re.fullmatch(r'(\S+)\s+-\s+(\S+)', line)
            if not match:
                errors.append(f'{path}: malformed manifest line: {line}')
                continue
            actual.add(match[1])
        missing = sorted(required - actual)
        missing_selected = sorted(predicted - actual - required)
        errors.extend(f'{path}: missing installed-baseline package {name}' for name in missing)
        errors.extend(f'{path}: missing selected package {name}' for name in missing_selected)
        manifests[str(path)] = {'package_count': len(actual), 'missing': missing,
                                'missing_selected': missing_selected,
                                'additional': sorted(actual - required)}

    result = {'installed_package_count': len(baseline['packages']),
              'required_apk_count': len(required), 'installed_to_current': mapping,
              'additional_selected_apk_names': sorted(predicted - required),
              'manifests': manifests, 'errors': errors}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    if errors:
        for error in errors:
            print(f'installed package baseline: {error}', file=sys.stderr)
        return 1
    print(f'Installed package baseline passed: {len(baseline["packages"])} installed '
          f'packages map to {len(required)} current APK names; '
          f'{len(predicted - required)} additional selected packages')
    return 0


if __name__ == '__main__':
    sys.exit(main())
