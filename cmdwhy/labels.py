"""用户对任务/目的的人工标注：覆盖启发式标签，按稳定 ID 持久化。"""

from __future__ import annotations

import json

from .util import atomic_write


def load(cfg):
    try:
        with open(cfg.labels_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"labels": {}}
    if not isinstance(data, dict):
        return {"labels": {}}
    data.setdefault("labels", {})
    return data


def save(cfg, data):
    cfg.ensure()
    atomic_write(cfg.labels_path, json.dumps(data, ensure_ascii=False, indent=2))


def set_label(cfg, uid, task=None, goal=None, purpose=None):
    data = load(cfg)
    entry = data["labels"].setdefault(uid, {})
    if task:
        entry["task"] = task
    if goal:
        entry["goal"] = goal
    if purpose:
        entry["purpose"] = purpose
    save(cfg, data)
    return entry


def clear(cfg, uid):
    data = load(cfg)
    removed = data["labels"].pop(uid, None)
    save(cfg, data)
    return removed


def apply(analysis, cfg):
    try:
        data = load(cfg)
    except Exception:
        return analysis
    if not data:
        return analysis
    labels = data.get("labels") or {}
    for ann in analysis.anns:
        event = analysis.event(ann.seq)
        entry = labels.get(getattr(event, "uid", ""))
        if not entry:
            continue
        context = analysis.contexts.get(ann.seq) if getattr(analysis, "contexts", None) else None
        if entry.get("task"):
            ann.task = entry["task"]
            if context is not None:
                context.label = entry["task"]
        if entry.get("goal"):
            ann.task_goal = entry["goal"]
            if context is not None:
                context.goal = entry["goal"]
        if entry.get("purpose"):
            ann.purpose = entry["purpose"]
            if context is not None:
                context.purpose = entry["purpose"]
        ann.add("人工标注：任务/目标/目的由用户确认")
    return analysis
