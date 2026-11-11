#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("check_lean", Path(__file__).resolve().parents[1] / "scripts/check-lean-firmware.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

class LeanChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def rootfs(self):
        self.write("sbin/sysupgrade", "#!/bin/sh\n")
        self.write("usr/share/luci/menu.d/luci-mod-system.json", json.dumps({"admin/system/flash": {}}))

    def test_clean_rootfs(self):
        self.rootfs()
        self.assertEqual(checker.check(rootfs=self.root), [])

    def test_default_ota_is_rejected(self):
        config = self.write("config", "CONFIG_DEFAULT_luci-app-naoki66-ota=y\n")
        self.assertTrue(checker.check(config=config))

    def test_optional_ota_is_rejected(self):
        config = self.write("config", "CONFIG_PACKAGE_luci-app-naoki66-ota=m\n")
        self.assertTrue(checker.check(config=config))

    def test_attended_common_config_is_rejected(self):
        config = self.write("config", "CONFIG_PACKAGE_attendedsysupgrade-common=y\n")
        self.assertTrue(checker.check(config=config))

    def test_attended_common_manifest_is_rejected(self):
        manifest = self.write("manifest", "base-files - 1\nluci-mod-system - 1\nairoha-pond - 4\nluci-app-onu - 26\nattendedsysupgrade-common - 1\n")
        self.assertEqual(len(checker.check(manifest=manifest)), 1)

    def test_attended_common_defaults_are_rejected(self):
        self.rootfs()
        self.write("etc/uci-defaults/50-attendedsysupgrade", "#!/bin/sh\n")
        self.assertTrue(checker.check(rootfs=self.root))

    def test_shared_dependencies_are_allowed(self):
        config = self.write("config", "CONFIG_PACKAGE_uclient-fetch=y\nCONFIG_PACKAGE_luci-mod-system=y\n")
        self.assertEqual(checker.check(config=config), [])

    def test_manifest_forbids_ota(self):
        manifest = self.write("manifest", "base-files - 1\nluci-mod-system - 1\nairoha-pond - 4\nluci-app-onu - 26\nluci-app-naoki66-ota - 1.0.0-r1\n")
        self.assertEqual(len(checker.check(manifest=manifest)), 1)

    def test_injected_theme_is_rejected(self):
        self.rootfs()
        self.write("usr/share/ucode/luci/template/themes/argon/page_scripts.ut", "L.require('view.naoki66_ota.notice');")
        self.assertTrue(checker.check(rootfs=self.root))

    def test_helper_is_rejected(self):
        self.rootfs()
        self.write("usr/libexec/naoki66-ota-fetch", "#!/bin/sh\n")
        self.assertTrue(checker.check(rootfs=self.root))

    def test_manual_upgrade_is_required(self):
        self.assertEqual(len(checker.check(rootfs=self.root)), 2)

if __name__ == "__main__":
    unittest.main()
