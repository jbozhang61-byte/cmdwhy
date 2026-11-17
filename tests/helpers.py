"""测试用的临时配置与样例。"""

from __future__ import annotations

import os
import shutil
import tempfile

from cmdwhy.config import Config


def temp_config():
    home = tempfile.mkdtemp(prefix="cmdwhy-test-")
    cfg = Config(home=home)
    cfg.sources = []
    cfg.ensure()
    return cfg, home


def cleanup(path):
    shutil.rmtree(path, ignore_errors=True)


def base_ts():
    return 1763341920.0


def write_history(path, lines):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for line in lines:
            fh.write(line + "\n")
    return path
