"""通用工具：终端着色、时间/路径格式化、文本相似度、原子写文件。"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import datetime

RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_cyan": "\033[96m",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


class Paint:
    """极简 ANSI 着色器，可整体关闭。"""

    def __init__(self, enabled=None):
        self.enabled = color_enabled() if enabled is None else bool(enabled)

    def __call__(self, text, *styles):
        text = "" if text is None else str(text)
        if not self.enabled or not text:
            return text
        codes = "".join(STYLES.get(s, "") for s in styles)
        if not codes:
            return text
        return codes + text + RESET

    def bold(self, text):
        return self(text, "bold")

    def dim(self, text):
        return self(text, "dim")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text or "")


def fmt_time(ts) -> str:
    if not ts:
        return "--:--:--"
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "--:--:--"


def fmt_date(ts) -> str:
    if not ts:
        return "未知日期"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return "未知日期"


def fmt_hm(ts) -> str:
    if not ts:
        return "--:--"
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M")
    except (ValueError, OSError, OverflowError):
        return "--:--"


def fmt_datetime(ts) -> str:
    if not ts:
        return "时间未知"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "时间未知"


def fmt_span(start, end) -> str:
    """把起止时间渲染成 09:12–09:40 或 11-17 09:12。"""
    if not start and not end:
        return "时间未知"
    if not start:
        return fmt_time(end)
    if not end or abs(end - start) < 60:
        return fmt_time(start)
    same_day = fmt_date(start) == fmt_date(end)
    if same_day:
        return "%s–%s" % (fmt_hm(start), fmt_hm(end))
    return "%s → %s" % (fmt_datetime(start), fmt_datetime(end))


def fmt_duration(seconds) -> str:
    if seconds is None:
        return "?"
    seconds = max(0.0, float(seconds))
    if seconds < 1:
        return "%dms" % int(seconds * 1000)
    if seconds < 60:
        return "%.0fs" % seconds if seconds >= 10 else "%.1fs" % seconds
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    if minutes < 60:
        return "%dm%02ds" % (minutes, rest)
    hours = minutes // 60
    return "%dh%02dm" % (hours, minutes % 60)


def fmt_duration_ms(ms) -> str:
    if ms is None:
        return ""
    return fmt_duration(ms / 1000.0)


def relative_time(ts, ref=None) -> str:
    import time as _time

    if not ts:
        return "时间未知"
    ref = ref or _time.time()
    delta = ref - ts
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return "%d 分钟前" % int(delta // 60)
    if delta < 86400:
        return "%d 小时前" % int(delta // 3600)
    if delta < 86400 * 30:
        return "%d 天前" % int(delta // 86400)
    return fmt_date(ts)


def short_path(path, home=None, width=34) -> str:
    """~/work/api 这样的短路径，过长时保留尾部目录。"""
    if not path:
        return "?"
    p = str(path).replace("\\", "/").rstrip("/") or "/"
    home = home if home is not None else os.path.expanduser("~")
    h = str(home or "").replace("\\", "/").rstrip("/")
    if h and (p == h or p.startswith(h + "/")):
        p = "~" + p[len(h):]
    if len(p) <= width:
        return p
    parts = [part for part in p.split("/") if part]
    if not parts:
        return p
    keep = []
    total = 0
    for part in reversed(parts):
        extra = len(part) + (1 if keep else 0)
        if total + extra > width - 2 and keep:
            break
        keep.append(part)
        total += extra
    tail = "/".join(reversed(keep))
    return "…/" + tail


def truncate(text, width=120, ellipsis="…") -> str:
    text = "" if text is None else str(text)
    text = text.replace("\r", " ").replace("\n", " ⏎ ")
    if width <= 0 or len(text) <= width:
        return text
    return text[: max(0, width - 1)] + ellipsis


def norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def first_line(text, width=0) -> str:
    line = ""
    for candidate in (text or "").splitlines():
        if candidate.strip():
            line = candidate.strip()
            break
    if width:
        return truncate(line, width)
    return line


def indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line else line for line in (text or "").splitlines())


def ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)
    return path


def atomic_write(path: str, text: str):
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    fd, tmp = tempfile.mkstemp(prefix=".cmdwhy-", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def append_line(path: str, line: str):
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line.rstrip("\n") + "\n")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def damerau(a: str, b: str) -> int:
    """Damerau-Levenshtein（最优字符串对齐），把相邻字母交换算作一次编辑。"""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la:
        return lb
    if not lb:
        return la
    prev2 = None
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[lb]


_KB_ROWS = (
    "1234567890-=",
    "qwertyuiop[]\\",
    "asdfghjkl;'",
    "zxcvbnm,./",
)


def _build_neighbors():
    table = {}
    for row in _KB_ROWS:
        for idx, ch in enumerate(row):
            near = set()
            if idx > 0:
                near.add(row[idx - 1])
            if idx + 1 < len(row):
                near.add(row[idx + 1])
            table.setdefault(ch, set()).update(near)
    for row_idx, row in enumerate(_KB_ROWS):
        for idx, ch in enumerate(row):
            for other_idx in (idx - 1, idx, idx + 1):
                if row_idx + 1 < len(_KB_ROWS) and 0 <= other_idx < len(_KB_ROWS[row_idx + 1]):
                    table.setdefault(ch, set()).add(_KB_ROWS[row_idx + 1][other_idx])
                if row_idx > 0 and 0 <= other_idx < len(_KB_ROWS[row_idx - 1]):
                    table.setdefault(ch, set()).add(_KB_ROWS[row_idx - 1][other_idx])
    return table


KEYBOARD_NEIGHBORS = _build_neighbors()


def keyboard_near(a: str, b: str) -> bool:
    """两个等长词是否只差一个"相邻键"的误触。"""
    if len(a) != len(b):
        return False
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diffs) != 1:
        return False
    i = diffs[0]
    return b[i] in KEYBOARD_NEIGHBORS.get(a[i], set())


def percent(part, whole, digits=1) -> str:
    if not whole:
        return "0%"
    return ("%." + str(digits) + "f%%") % (100.0 * part / whole)


def bar(fraction, width=18, fill="#", empty="·") -> str:
    fraction = max(0.0, min(1.0, float(fraction or 0)))
    filled = int(round(width * fraction))
    return fill * filled + empty * (width - filled)


def shell_quote(arg: str) -> str:
    if re.match(r"^[A-Za-z0-9_@%+=:,./-]+$", arg or ""):
        return arg
    return "'" + (arg or "").replace("'", "'\\''") + "'"


def unique(items):
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def plural(n, one="条", many=None):
    return "%d %s" % (n, one if n == 1 else (many or one))


def json_default(obj):
    try:
        return obj.to_dict()
    except AttributeError:
        return str(obj)
