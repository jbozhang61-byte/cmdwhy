"""配置与数据目录：$CMDWHY_HOME 或 ~/.local/share/cmdwhy。"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from .util import read_json, write_json

CONFIG_VERSION = 1


def default_home() -> str:
    env = os.environ.get("CMDWHY_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(os.path.expandvars(env)))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "cmdwhy")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "cmdwhy")


def candidate_sources():
    home = os.path.expanduser("~")
    return [
        os.path.join(home, ".bash_history"),
        os.path.join(home, ".zsh_history"),
        os.path.join(home, ".local", "share", "fish", "fish_history"),
    ]


def default_sources():
    return [path for path in candidate_sources() if os.path.exists(path)]


@dataclass
class Config:
    home: str = ""
    sources: list = field(default_factory=list)
    idle_gap: int = 1800
    window: int = 8
    context_window: int = 20
    redact: bool = True
    color: str = "auto"
    learn: bool = True
    autopilot: str = "suggest"
    autocorrect: bool = False
    max_events: int = 5000
    ignore_prefixes: list = field(default_factory=lambda: ["cmdwhy", "cw diagnose", "cw fix"])
    sources_configured: bool = False
    version: int = CONFIG_VERSION

    def __post_init__(self):
        if not self.home:
            self.home = default_home()

    # ---- 路径 ----
    @property
    def config_path(self) -> str:
        return os.path.join(self.home, "config.json")

    @property
    def store_path(self) -> str:
        return os.path.join(self.home, "events.jsonl")

    @property
    def cache_path(self) -> str:
        return os.path.join(self.home, "cache.db")

    @property
    def repairs_path(self) -> str:
        return os.path.join(self.home, "repairs.json")

    @property
    def index_path(self) -> str:
        return os.path.join(self.home, "index.db")

    @property
    def knowledge_path(self) -> str:
        return os.path.join(self.home, "knowledge.json")

    @property
    def hooks_dir(self) -> str:
        return os.path.join(self.home, "hooks")

    @property
    def reports_dir(self) -> str:
        return os.path.join(self.home, "reports")

    def ensure(self) -> "Config":
        os.makedirs(self.home, exist_ok=True)
        os.makedirs(self.hooks_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)
        if not os.path.exists(self.config_path):
            self.save()
        return self

    # ---- 读写 ----
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "sources": list(self.sources),
            "idle_gap": self.idle_gap,
            "window": self.window,
            "context_window": self.context_window,
            "redact": self.redact,
            "color": self.color,
            "learn": self.learn,
            "autopilot": self.autopilot,
            "autocorrect": self.autocorrect,
            "max_events": self.max_events,
            "ignore_prefixes": list(self.ignore_prefixes),
        }

    def save(self):
        os.makedirs(self.home, exist_ok=True)
        write_json(self.config_path, self.to_dict())

    def expand_sources(self, specs=None):
        out = []
        for spec in (self.sources if specs is None else specs):
            spec = os.path.expanduser(os.path.expandvars(str(spec)))
            matches = sorted(glob.glob(spec))
            if not matches and os.path.exists(spec):
                matches = [spec]
            out.extend(matches)
        seen = []
        for path in out:
            if path not in seen:
                seen.append(path)
        return seen


def load_config(home=None) -> Config:
    home = os.path.abspath(os.path.expanduser(home or default_home()))
    data = read_json(os.path.join(home, "config.json"), {}) or {}
    cfg = Config(home=home)
    if isinstance(data, dict):
        for key in ("idle_gap", "window", "context_window", "max_events"):
            if isinstance(data.get(key), int) and data[key] > 0:
                setattr(cfg, key, data[key])
        for key in ("redact", "learn", "autocorrect"):
            if isinstance(data.get(key), bool):
                setattr(cfg, key, data[key])
        if data.get("autopilot") in ("off", "suggest", "auto"):
            cfg.autopilot = data["autopilot"]
        if isinstance(data.get("sources"), list):
            cfg.sources = [str(item) for item in data["sources"]]
            cfg.sources_configured = True
        if isinstance(data.get("ignore_prefixes"), list):
            cfg.ignore_prefixes = [str(item) for item in data["ignore_prefixes"]]
        if data.get("color") in ("auto", "always", "never"):
            cfg.color = data["color"]
    if not cfg.sources_configured and not cfg.sources:
        cfg.sources = default_sources()
    return cfg


def config_for(home=None) -> Config:
    return load_config(home).ensure()
