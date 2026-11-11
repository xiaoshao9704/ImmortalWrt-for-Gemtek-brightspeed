#!/usr/bin/env python3
"""Reject remote firmware updaters in config, manifest and the built rootfs."""
import argparse
import json
from pathlib import Path
import re

FORBIDDEN = re.compile(r"^(?:luci-app-naoki66-ota|naoki66-ota.*|ac-agent|luci-app-ac-agent|luci-i18n-ac-agent-.*|luci-app-attendedsysupgrade|luci-i18n-attendedsysupgrade-.*|attendedsysupgrade-common|auc|owut|pbr|luci-app-pbr|luci-i18n-pbr-.*)$")

def check(config=None, manifest=None, rootfs=None):
    errors = []
    if config:
        for line in Path(config).read_text().splitlines():
            match = re.fullmatch(r"CONFIG_(?:PACKAGE|DEFAULT)_(.+)=(?:y|m)", line)
            if match and FORBIDDEN.fullmatch(match[1]):
                errors.append("forbidden config: " + match[1])
    if manifest:
        names = {line.split()[0] for line in Path(manifest).read_text().splitlines() if line.strip()}
        errors += ["forbidden package: " + name for name in sorted(names) if FORBIDDEN.fullmatch(name)]
        for name in ("base-files", "luci-mod-system", "airoha-pond", "luci-app-onu"):
            if name not in names:
                errors.append("missing required package: " + name)
    if rootfs:
        root = Path(rootfs)
        if not root.is_dir():
            errors.append("rootfs does not exist: " + str(root))
            return errors
        for path in root.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if "naoki66-ota" in rel or "naoki66_ota" in rel or path.name in ("ac-agent", "auc", "owut"):
                errors.append("forbidden rootfs path: " + rel)
            if path.name in ("50-attendedsysupgrade", "attendedsysupgrade", "luci-app-attendedsysupgrade.json"):
                errors.append("attended upgrade rootfs path: " + rel)
            if path.is_file() and not path.is_symlink() and path.suffix in (".ut", ".htm", ".js", ".json"):
                text = path.read_text(errors="replace")
                if "view.naoki66_ota" in text or '"admin/system/ota"' in text:
                    errors.append("OTA injection: " + rel)
        if not (root / "sbin/sysupgrade").is_file():
            errors.append("manual sysupgrade missing")
        menu = root / "usr/share/luci/menu.d/luci-mod-system.json"
        try:
            if "admin/system/flash" not in json.loads(menu.read_text()):
                errors.append("manual LuCI flash menu missing")
        except (OSError, ValueError):
            errors.append("manual LuCI flash menu unreadable")
    return errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--manifest")
    parser.add_argument("--rootfs")
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.error("at least one input is required")
    errors = check(**vars(args))
    if errors:
        raise SystemExit("\n".join(errors))
    print("Lean firmware checks passed for all supplied inputs.")
