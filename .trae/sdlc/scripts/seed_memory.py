#!/usr/bin/env python3
"""Create the TRAE project-memory skeleton for every SDLC agent (§M-2).

Idempotent: existing MEMORY.md files are never overwritten.
"""
from __future__ import annotations

import io
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASE = os.path.join(ROOT, ".trae", "sdlc", "agent-memory")

AGENTS = {
    "pm-orchestrator": "PM",
    "requirement-analyst": "RA",
    "system-architect": "SA",
    "software-developer": "SD",
    "test-engineer": "TE",
    "devops-engineer": "DE",
    "kb-curator": "KC",
    "agent-builder": "AB",
}

TEMPLATE = """# {agent} 项目记忆 — {project}

> TRAE 不自动注入记忆：本文件由对应 `sdlc-*` 技能在开始时**显式 Read**。
> 只允许 agent 自己追加「待验证」区；「已验证」「用户偏好与禁止项」由 kb-curator 维护。

## 已验证
<!-- - [M-{abbr}-001] 一句话经验 — conf 0.8 · 证据 GR-B-002 / DEF-003 / commit abc123 / 用户确认 · 首见 YYYY-MM-DD · 命中 1 -->

## 用户偏好与禁止项
<!-- - [M-{abbr}-002] … — 来源：用户原话 / YYYY-MM-DD -->

## 待验证
<!-- - [P-{abbr}-001] 一句话 — 自记 YYYY-MM-DD · 证据（可空） -->
"""


def main() -> int:
    created = 0
    for agent, abbr in AGENTS.items():
        path = os.path.join(BASE, agent, "MEMORY.md")
        if os.path.isfile(path):
            print("KEEP  %s" % os.path.relpath(path, ROOT))
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(TEMPLATE.format(agent=agent, project="{PROJECT_NAME}", abbr=abbr))
        created += 1
        print("SEED  %s" % os.path.relpath(path, ROOT))
    print("MEMORY_SEEDED created=%d total=%d" % (created, len(AGENTS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
