"""修复链的简单概率评分：logistic causal score，不是严格的因果推断。"""

from __future__ import annotations

import math

from .model import command_head, core_signature

MUTATION_HINTS = (
    "install", "chmod", "chown", "kill", "mkdir", "venv", "pull", "rebase",
    "systemctl", "usermod", "apt", "pip", "npm", "composer", "bundle",
)


def _sigmoid(value):
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


def chain_probability(chain, events, errors=None):
    """根据时间距离、重跑相似度、修复动作、验证状态估算因果概率。"""
    by_seq = {event.seq: event for event in events}
    failure = by_seq.get(chain.fail_seq)
    verify = by_seq.get(chain.verify_seq) if chain.verify_seq else None
    retry = by_seq.get(chain.retry_seq) if chain.retry_seq else None
    error = errors.get(chain.fail_seq) if errors else None

    anchor = chain.verify_seq or chain.retry_seq or chain.fail_seq
    distance = max(0, anchor - chain.fail_seq)
    logit = -1.1
    logit -= min(1.2, distance * 0.08)

    if failure is not None and retry is not None:
        if core_signature(failure.cmd) == core_signature(retry.cmd):
            logit += 1.2
        elif command_head(failure.cmd) == command_head(retry.cmd):
            logit += 0.6

    step_commands = [command for _seq, command in (chain.steps or [])]
    if any(any(hint in command.lower() for hint in MUTATION_HINTS) for command in step_commands):
        logit += 0.8
    if 1 <= len(step_commands) <= 3:
        logit += 0.2
    if chain.verified:
        logit += 1.8
    if verify is not None and verify.exit_code == 0:
        logit += 0.4
    if error is not None and error.confidence == "high":
        logit += 0.5
    if not step_commands and not chain.verified:
        logit -= 0.6
    return round(_sigmoid(logit), 4)


def label(probability):
    if probability >= 0.8:
        return "高"
    if probability >= 0.55:
        return "中"
    return "低"
