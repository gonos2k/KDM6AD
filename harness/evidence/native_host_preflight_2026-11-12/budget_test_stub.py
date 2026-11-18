#!/usr/bin/env python3
"""Fixed subprocess scenarios for synthetic budget tests; no model imports."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        return 2
    scenario = sys.argv[1]
    if scenario == "success":
        time.sleep(0.15)
        Path("out.bin").write_bytes(b"ok")
        return 0
    if scenario == "fail":
        return 7
    if scenario == "sleep":
        time.sleep(20)
        return 0
    if scenario == "_grandchild_ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(20)
        return 0
    if scenario in ("term_ignoring_child", "residual_child"):
        if scenario == "term_ignoring_child":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                os.path.realpath(__file__),
                "_grandchild_ignore",
            ]
        )
        if scenario == "term_ignoring_child":
            time.sleep(20)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
