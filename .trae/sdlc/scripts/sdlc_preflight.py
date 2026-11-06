#!/usr/bin/env python3
"""TRAE equivalent of `.claude/hooks/sdlc_pre_agent.py` + suite preflight.

Claude Code enforces "the main session must be at the repository root before
spawning an SDLC subagent" with a PreToolUse hook. TRAE has no hook runtime,
so the PM must run this script **before every subagent invocation**, and the
subagent skills may run it too.

Usage:
    python .trae/sdlc/scripts/sdlc_preflight.py --check-cwd
    python .trae/sdlc/scripts/sdlc_preflight.py --check-flow-start
    python .trae/sdlc/scripts/sdlc_preflight.py --check-all

Exit codes:
    0  OK
    2  cwd is not the repository root (same rule as the Claude hook)
    3  profile missing / DRAFT, or a required preflight item failed

Never raises: unexpected errors degrade to a report, not a crash.
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TRAE = os.path.join(ROOT, ".trae")
SKILLS = os.path.join(TRAE, "skills")
RUNTIME = os.path.join(TRAE, "sdlc")
PROFILE = os.path.join(RUNTIME, "project_profile.md")

SKILL_NAMES = [
    "sdlc-orchestrator",
    "sdlc-shared-protocol",
    "sdlc-requirement-analyst",
    "sdlc-system-architect",
    "sdlc-software-developer",
    "sdlc-test-engineer",
    "sdlc-devops-engineer",
    "sdlc-kb-curator",
    "sdlc-agent-builder",
]


def repo_root() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return os.path.realpath(out.stdout.strip())
    except Exception:
        pass
    return os.path.realpath(ROOT)


def check_cwd() -> int:
    root = repo_root()
    cwd = os.path.realpath(os.getcwd())
    if root == cwd:
        print("CWD_OK %s" % cwd)
        return 0
    print(
        "CWD_DENIED 当前目录 %s 不是仓库根 %s。子代理的记忆与工作区按仓库根定位；"
        "请先回到仓库根再加载 sdlc-* 技能（对应 Claude 的 sdlc_pre_agent.py）。"
        % (cwd, root)
    )
    return 2


def read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def profile_status() -> tuple[str, str]:
    if not os.path.isfile(PROFILE):
        return "MISSING", ""
    head = read(PROFILE)[:4000]
    m = re.search(r"<status>\s*([A-Z_]+)\s*</status>", head)
    return (m.group(1) if m else "UNKNOWN"), PROFILE


def check_flow_start() -> int:
    status, path = profile_status()
    if status == "MISSING":
        print("PROFILE_MISSING 先生成 .trae/sdlc/project_profile.md（status=DRAFT），"
              "请用户逐项确认后改为 APPROVED 再启动流程。")
        return 3
    if status != "APPROVED":
        print("PROFILE_NOT_APPROVED status=%s path=%s；请用户确认后改为 APPROVED。" % (status, path))
        return 3
    print("PROFILE_APPROVED %s" % path)
    return 0


def check_all() -> int:
    problems: list[str] = []

    # 1) skills present + frontmatter name matches directory
    for name in SKILL_NAMES:
        path = os.path.join(SKILLS, name, "SKILL.md")
        if not os.path.isfile(path):
            problems.append("missing skill: %s" % name)
            continue
        head = read(path)[:400]
        if not head.startswith("---"):
            problems.append("%s: missing frontmatter" % name)
        elif not re.search(r"^name:\s*%s\s*$" % re.escape(name), head, re.M):
            problems.append("%s: frontmatter name mismatch" % name)

    # 2) no leaked .claude runtime references in bodies
    for name in SKILL_NAMES:
        path = os.path.join(SKILLS, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        body = read(path)
        body = re.sub(r"^>.*复刻自.*$", "", body, flags=re.M)
        for ref in re.findall(r"\.claude/(?:agents|hooks|agent-memory)[^\s`)]*", body):
            problems.append("%s: residual %s" % (name, ref))

    # 3) runtime artifacts
    for rel in ("project_profile.template.md", "suite_config.md",
                "knowledge_base/generic/pm-orchestrator.md",
                "scripts/kb_inbox.py", "scripts/webfetch_guard.py"):
        if not os.path.isfile(os.path.join(RUNTIME, rel)):
            problems.append("missing runtime file: .trae/sdlc/%s" % rel)

    # 4) phase_status XML well-formed (skip legacy Markdown files)
    for rel in glob.glob(os.path.join(RUNTIME, "**", "phase_status.md"), recursive=True) + \
               glob.glob(os.path.join(ROOT, "docs", "**", "phase_status.md"), recursive=True):
        with io.open(rel, encoding="utf-8", errors="replace") as fh:
            head = fh.read(4096)
        probe = re.sub(r"^(?:\s|<!--.*?-->|<\?xml.*?\?>)*", "", head, flags=re.S)
        if not probe.startswith("<phase_status"):
            print("SKIP_NON_XML %s" % rel)
            continue
        try:
            ET.parse(rel)
        except Exception as exc:  # noqa: BLE001
            problems.append("phase_status not well-formed: %s (%s)" % (rel, exc))

    # 5) profile status (informational only)
    status, _ = profile_status()

    # 6) memory seeds
    for agent in ("pm-orchestrator", "requirement-analyst", "system-architect",
                  "software-developer", "test-engineer", "devops-engineer",
                  "kb-curator", "agent-builder"):
        if not os.path.isfile(os.path.join(RUNTIME, "agent-memory", agent, "MEMORY.md")):
            problems.append("missing memory seed: agent-memory/%s/MEMORY.md" % agent)

    if problems:
        print("PREFLIGHT_FAILED (%d)" % len(problems))
        for p in problems:
            print("  - " + p)
        return 3

    print("PREFLIGHT_OK skills=%d profile=%s" % (len(SKILL_NAMES), status))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-cwd", action="store_true")
    ap.add_argument("--check-flow-start", action="store_true")
    ap.add_argument("--check-all", action="store_true")
    args = ap.parse_args()

    if args.check_cwd:
        return check_cwd()
    if args.check_flow_start:
        return check_flow_start()
    if args.check_all:
        return check_all()

    rc = check_cwd()
    if rc != 0:
        return rc
    return check_all()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the run
        print("PREFLIGHT_ERROR %s" % exc)
        sys.exit(0)
