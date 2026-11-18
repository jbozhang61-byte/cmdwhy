"""用户修复链纠正：把“这不是修复”持久化，分析时应用。"""

from __future__ import annotations

import json
import os

from .util import atomic_write


def load(cfg):
    path = cfg.repairs_path
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"rejected": {}, "accepted": {}}
    if not isinstance(data, dict):
        return {"rejected": {}, "accepted": {}}
    data.setdefault("rejected", {})
    data.setdefault("accepted", {})
    return data


def save(cfg, data):
    cfg.ensure()
    atomic_write(cfg.repairs_path, json.dumps(data, ensure_ascii=False, indent=2))


def reject(cfg, failure_uid, repair_uid=None):
    data = load(cfg)
    data["rejected"][failure_uid] = repair_uid or ""
    data["accepted"].pop(failure_uid, None)
    save(cfg, data)


def accept(cfg, failure_uid):
    data = load(cfg)
    data["rejected"].pop(failure_uid, None)
    data["accepted"][failure_uid] = True
    save(cfg, data)


def apply(analysis, data):
    rejected = data.get("rejected") or {}
    accepted = data.get("accepted") or {}
    for ann in analysis.anns:
        event = analysis.event(ann.seq)
        if event.uid in rejected:
            ann.fix_of = []
            ann.steps = []
            ann.verified = False
            ann.verified_at = None
            ann.role = "other"
            ann.note = "用户标记：这不是修复"
            ann.add("用户已标记这条修复链不成立")
        elif event.uid in accepted and ann.fix_of:
            ann.confidence = "high"
            ann.add("用户确认这条修复链成立")
    return analysis
