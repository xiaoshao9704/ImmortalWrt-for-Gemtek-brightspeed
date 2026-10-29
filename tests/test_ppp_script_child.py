#!/usr/bin/env python3
"""Host regression for PR #638, using functions from a prepared ppp source tree.

Usage: python3 tests/test_ppp_script_child.py --source /tmp/ppp-2.5.4
Compile and run the actual fork / environment / exec functions with a guarded
TDB stub. No root, PPP device, network changes or target hardware required.
This is not a PPPoE negotiation or full pppd integration test.
"""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest


def function(source, name):
    # These upstream functions have unindented opening/closing braces.
    match = re.search(r"^" + name + r"\([^\n]*\)\n\{.*?^\}", source, re.M | re.S)
    if not match:
        raise ValueError(f"cannot find upstream function {name}")
    return match.group(0)


PREAMBLE = r'''
#define _GNU_SOURCE
#define HAVE_FEXECVE 1
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <syslog.h>
#include <unistd.h>
static int fd_devnull, log_to_fd = -1, devfd = -1, fd_ppp = -1;
static int debug, strict_script_checks, fork_notifier, s_env_nalloc;
static int script_status = -1, db_closed, db_updates;
static char **script_env;
static int database;
static void *pppdb = &database;
static struct { void (*close)(void); } channel, *the_channel = &channel;
#define PPP_FT_EXEC 1
#define slprintf snprintf
static void error(const char *fmt, ...) { (void)fmt; }
static void dbglog(const char *fmt, ...) { (void)fmt; }
static void fatal(const char *fmt, ...) { (void)fmt; _exit(90); }
static void ppp_sys_close(void) {}
static void notify(int notifier, int status) { (void)notifier; (void)status; }
static ssize_t complete_read(int fd, void *buf, size_t n) { return read(fd, buf, n); }
static void tdb_close(void *db) {
    if (db != &database || db_closed) _exit(85);
    db_closed = 1;
}
static void update_db_entry(void) {
    /* A closed TDB must never be used after fork. Avoid undefined behavior
       while detecting the same lifetime error deterministically. */
    if (pppdb != &database || db_closed) _exit(86);
    ++db_updates;
}
static void add_db_key(const char *key) { (void)key; update_db_entry(); }
static void delete_db_key(const char *key) { (void)key; update_db_entry(); }
static bool ppp_check_access(int fd, const char *path, int type) {
    struct stat st;
    (void)path; (void)type;
    return fstat(fd, &st) == 0 && S_ISREG(st.st_mode) && (st.st_mode & 0111);
}
static void record_child(int pid, const char *p, void (*done)(void *), void *arg, int k) {
    (void)pid; (void)p; (void)done; (void)arg; (void)k;
}
static void forget_child(int pid, int status) { (void)pid; script_status = status; }
static void update_script_environment(void) {}
static void reopen_log(void) {}
'''

MAIN = r'''
int main(int argc, char **argv) {
    if (argc != 5) return 91;
    strict_script_checks = atoi(argv[3]);
    if (atoi(argv[4])) pppdb = NULL;
    void *parent_db = pppdb;
    fd_devnull = open("/dev/null", O_RDWR);
    if (fd_devnull < 0) return 92;
    /* Exercise both creating and replacing a script environment entry. */
    ppp_script_setenv("PPP_SCRIPT_INSTANCE", "previous", 0);
    char *args[] = {argv[1], argv[2], NULL};
    if (run_program(argv[1], args, 1, NULL, NULL, 1, "ip-up") <= 0) return 93;
    if (pppdb != parent_db || db_closed) return 94;
    int before = db_updates;
    ppp_script_setenv("PARENT_STILL_LIVE", "yes", 0);
#ifdef PPP_WITH_TDB
    if (parent_db && db_updates <= before) return 95;
#else
    (void)before;
#endif
    if (!WIFEXITED(script_status)) return 96;
    return WEXITSTATUS(script_status);
}
'''


class ScriptChildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ppp-script-child-")
        cls.root = Path(cls.tmp.name)
        text = (SOURCE / "pppd/main.c").read_text()
        bodies = []
        for typ, name in [("pid_t", "ppp_safe_fork"), ("static bool", "add_script_env"),
                          ("void", "ppp_script_setenv"), ("pid_t", "run_program")]:
            bodies.append(typ + "\n" + function(text, name))
        cls.code = PREAMBLE + "\n".join(bodies) + MAIN
        cls.hook = cls.root / "ip-up"
        cls.hook.write_text('#!/bin/sh\nprintf "%s\\n" "$PPP_SCRIPT_INSTANCE" > "$1"\n')
        cls.hook.chmod(0o700)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, tdb=True, strict=True, null_db=False, mutant=False):
        code = self.code
        if mutant:
            # Negative control: restore only the dangling-pointer defect.
            code, count = re.subn(r"pppdb = NULL;[^\n]*", "/* regression restored */", code, count=1)
            self.assertEqual(count, 1)
        source = self.root / "test.c"
        binary = self.root / "test"
        marker = self.root / "hook.out"
        marker.unlink(missing_ok=True)
        source.write_text(code)
        command = shlex.split(os.environ.get("CC", "cc")) + ["-std=gnu11", "-O2"]
        if tdb:
            command += ["-DPPP_WITH_TDB"]
        subprocess.run(command + [str(source), "-o", str(binary)], check=True,
                       capture_output=True, text=True, timeout=30)
        result = subprocess.run([str(binary), str(self.hook), str(marker),
                                 str(int(strict)), str(int(null_db))], timeout=10)
        self.assertEqual(result.returncode, 86 if mutant else 0)
        if mutant:
            self.assertFalse(marker.exists(), "broken child must fail before executing hook")
        else:
            self.assertEqual(marker.read_text(), "ip-up\n")

    def test_tdb_strict_exec(self):
        self.run_case()

    def test_tdb_path_exec(self):
        self.run_case(strict=False)

    def test_null_database(self):
        self.run_case(null_db=True)

    def test_without_tdb(self):
        self.run_case(tdb=False)

    def test_negative_control_dies_before_hook(self):
        self.run_case(mutant=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args, rest = parser.parse_known_args()
    SOURCE = args.source
    unittest.main(argv=[__file__] + rest)
