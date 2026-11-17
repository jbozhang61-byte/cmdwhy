"""错误知识库：把"错误签名 -> 当时真正修好它的命令"沉淀下来。

下次遇到同签名（例如 PERM:dpkg-lock、MODULE:flask、PORT:3000）时，
cmdwhy 会把你以前验证有效的修法直接检索出来，而不是给通用建议。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

from .errors import normalize_error_text
from .util import read_json, write_json

KB_VERSION = 1


@dataclass
class Remedy:
    signature: str
    category: str
    steps: list
    count: int = 0
    verified: int = 0
    last_ts: float = 0.0
    sample: str = ""

    @property
    def command(self) -> str:
        return " && ".join(self.steps)

    def to_dict(self):
        return {
            "signature": self.signature,
            "category": self.category,
            "steps": list(self.steps),
            "count": self.count,
            "verified": self.verified,
            "last_ts": self.last_ts,
            "sample": self.sample,
        }


class Knowledge:
    def __init__(self, path):
        self.path = path
        data = read_json(path, None) or {}
        self.updated = float(data.get("updated") or 0)
        self.entries = data.get("entries") or {}

    # ---- 学习 ----
    def learn(self, analysis) -> int:
        learned = 0
        for ann in analysis.anns:
            if ann.status not in ("fail", "suspected"):
                continue
            if not ann.steps or ann.error is None:
                continue
            signature = getattr(ann.error, "signature", "") or getattr(ann.error, "category", "")
            if not signature:
                continue
            category = getattr(ann.error, "category", "")
            entry = self.entries.setdefault(
                signature,
                {
                    "category": category,
                    "count": 0,
                    "first_ts": 0.0,
                    "last_ts": 0.0,
                    "remedies": {},
                    "samples": [],
                    "norm": "",
                },
            )
            entry["category"] = entry.get("category") or category
            entry["count"] = int(entry.get("count") or 0) + 1
            event = analysis.event(ann.seq)
            entry["last_ts"] = max(float(entry.get("last_ts") or 0), event.ts or 0)
            if not entry.get("first_ts"):
                entry["first_ts"] = event.ts or 0
            reason = getattr(ann.error, "detail", "") or ""
            samples = entry.setdefault("samples", [])
            if reason and reason not in samples and len(samples) < 3:
                samples.append(reason)
            if not entry.get("norm"):
                entry["norm"] = normalize_error_text(getattr(ann.error, "text", "") or reason)
            key = " && ".join(ann.steps)
            remedy = entry["remedies"].setdefault(
                key,
                {"steps": list(ann.steps), "count": 0, "verified": 0, "last_ts": 0.0},
            )
            remedy["count"] = int(remedy.get("count") or 0) + 1
            if ann.verified:
                remedy["verified"] = int(remedy.get("verified") or 0) + 1
            remedy["last_ts"] = max(float(remedy.get("last_ts") or 0), event.ts or 0)
            learned += 1
        if learned:
            self.updated = time.time()
            self.save()
        return learned

    # ---- 检索 ----
    def lookup(self, signature, category=None, limit=3) -> list:
        if not signature and not category:
            return []
        results = []
        entry = self.entries.get(signature)
        if entry:
            results.extend(self._remedies(signature, entry))
        if category:
            for sig, other in self.entries.items():
                if sig == signature:
                    continue
                if (other.get("category") or "") == category:
                    results.extend(self._remedies(sig, other, weight=0.75))
        results.sort(key=lambda item: (-(item.count + item.verified * 2), -item.last_ts))
        seen = set()
        unique = []
        for item in results:
            if item.command in seen:
                continue
            seen.add(item.command)
            unique.append(item)
        return unique[:limit]

    def lookup_text(self, text, category=None, limit=3, threshold=0.55):
        """按错误原文的相似度检索：同一类错误换个 PID / 路径也能认出来。"""
        target = normalize_error_text(text)
        if not target:
            return []
        scored = []
        for signature, entry in self.entries.items():
            candidate = entry.get("norm") or ""
            if not candidate:
                samples = entry.get("samples") or []
                candidate = normalize_error_text(samples[0]) if samples else ""
            if not candidate:
                continue
            ratio = SequenceMatcher(None, target, candidate).ratio()
            if category and entry.get("category") == category:
                ratio += 0.05
            if ratio >= threshold:
                scored.append((ratio, signature, entry))
        scored.sort(key=lambda item: -item[0])
        results = []
        for ratio, signature, entry in scored[:3]:
            results.extend(self._remedies(signature, entry, weight=min(1.0, ratio)))
        results.sort(key=lambda item: -(item.count + item.verified * 2))
        seen = set()
        unique = []
        for item in results:
            if item.command in seen:
                continue
            seen.add(item.command)
            unique.append(item)
        return unique[:limit]

    def _remedies(self, signature, entry, weight=1.0):
        out = []
        category = entry.get("category") or ""
        samples = entry.get("samples") or []
        for data in (entry.get("remedies") or {}).values():
            steps = data.get("steps") or []
            if not steps:
                continue
            out.append(
                Remedy(
                    signature=signature,
                    category=category,
                    steps=list(steps),
                    count=int(round(int(data.get("count") or 1) * weight)),
                    verified=int(data.get("verified") or 0),
                    last_ts=float(data.get("last_ts") or 0),
                    sample=(samples[0] if samples else ""),
                )
            )
        return out

    def occurrences(self, signature) -> int:
        entry = self.entries.get(signature)
        return int(entry.get("count") or 0) if entry else 0

    def all_signatures(self):
        return sorted(self.entries.keys())

    def summary(self):
        total = sum(int(item.get("count") or 0) for item in self.entries.values())
        verified = 0
        for entry in self.entries.values():
            for remedy in (entry.get("remedies") or {}).values():
                verified += int(remedy.get("verified") or 0)
        return {
            "signatures": len(self.entries),
            "occurrences": total,
            "verified_fixes": verified,
            "updated": self.updated,
        }

    def save(self):
        write_json(
            self.path,
            {"version": KB_VERSION, "updated": self.updated, "entries": self.entries},
        )

    def clear(self):
        self.entries = {}
        self.updated = time.time()
        self.save()

    def export(self):
        return {"version": KB_VERSION, "updated": self.updated, "entries": self.entries}


def load_knowledge(cfg) -> Knowledge:
    os.makedirs(cfg.home, exist_ok=True)
    return Knowledge(cfg.knowledge_path)
