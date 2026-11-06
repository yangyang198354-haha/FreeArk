#!/usr/bin/env python3
"""Self-test for the TRAE SDLC agent suite.

Covers what TRAE cannot enforce with hooks:
  1. structural contract (9 skills, frontmatter, no leaked .claude paths)
  2. preflight hook equivalent (cwd guard + suite checks)
  3. kb_inbox hook equivalent (response validation, idempotent append, redaction)
  4. webfetch guard hook equivalent (allow / deny / citations / WebSearch)

Usage:  python .trae/sdlc/scripts/suite_selftest.py
Exit:   0 all checks passed, 1 any failure.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPTS = os.path.join(ROOT, ".trae", "sdlc", "scripts")
SKILLS = os.path.join(ROOT, ".trae", "skills")

SKILL_NAMES = [
    "sdlc-orchestrator", "sdlc-shared-protocol", "sdlc-requirement-analyst",
    "sdlc-system-architect", "sdlc-software-developer", "sdlc-test-engineer",
    "sdlc-devops-engineer", "sdlc-kb-curator", "sdlc-agent-builder",
]

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    results.append((ok, label))
    print(("PASS  " if ok else "FAIL  ") + label + (("  | " + detail) if detail and not ok else ""))


def run(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    proc = subprocess.run([sys.executable] + args, cwd=cwd or ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def structural() -> None:
    for name in SKILL_NAMES:
        path = os.path.join(SKILLS, name, "SKILL.md")
        if not os.path.isfile(path):
            check(False, "skill exists: %s" % name)
            continue
        text = io.open(path, encoding="utf-8").read()
        head = text[:300]
        ok = head.startswith("---") and ("name: %s" % name) in head and "description:" in head
        check(ok, "frontmatter: %s" % name)

        body = "\n".join(l for l in text.splitlines() if not l.startswith(">"))
        leaks = [t for t in ("/.claude/agents", "claude --agent", "subagent_type") if t in body]
        check(not leaks, "no leaked Claude invocation in %s" % name, ",".join(leaks))

    # protocol sections
    proto = io.open(os.path.join(SKILLS, "sdlc-shared-protocol", "SKILL.md"), encoding="utf-8").read()
    for sec in ("## A.", "## B.", "## C.", "## E.", "## J.", "## L.", "## M.", "## N."):
        check(sec in proto, "protocol section %s" % sec)

    # hook equivalence commands documented
    orch = io.open(os.path.join(SKILLS, "sdlc-orchestrator", "SKILL.md"), encoding="utf-8").read()
    for cmd in ("sdlc_preflight.py", "kb_inbox.py", "webfetch_guard.py"):
        check(cmd in orch, "orchestrator references %s" % cmd)


def preflight() -> None:
    rc, out = run([os.path.join(SCRIPTS, "sdlc_preflight.py"), "--check-all"])
    check(rc == 0, "preflight --check-all", out.strip().splitlines()[-1] if out.strip() else "")

    rc, out = run([os.path.join(SCRIPTS, "sdlc_preflight.py"), "--check-cwd"])
    check(rc == 0, "preflight --check-cwd at repo root", out.strip())

    sub = os.path.join(ROOT, ".trae")
    rc, out = run([os.path.join(SCRIPTS, "sdlc_preflight.py"), "--check-cwd"], cwd=sub)
    check(rc == 2, "preflight denies non-root cwd (exit 2)", out.strip())


def kb_inbox() -> None:
    tmp = tempfile.mkdtemp(prefix="sdlc_selftest_")
    try:
        bad = os.path.join(tmp, "bad.md")
        io.open(bad, "w", encoding="utf-8").write("no response block here")
        rc, out = run([os.path.join(SCRIPTS, "kb_inbox.py"), "--check-response", "--text-file", bad])
        check(rc == 3, "kb_inbox rejects missing <agent_response> (exit 3)", out.strip())

        good = os.path.join(tmp, "good.md")
        io.open(good, "w", encoding="utf-8").write(
            "<agent_response>\n"
            "  <invocation_id>demo-A-001</invocation_id>\n"
            "  <agent_id>requirement-analyst</agent_id>\n"
            "  <status>SUCCESS</status>\n"
            "  <kb_proposals>\n"
            "    <proposal scope=\"generic\" evidence=\"GR-A-001\">先在画像里登记测试命令，可减少返工</proposal>\n"
            "    <proposal scope=\"project\" evidence=\"\">含口令 password=hunter2 的条目应被脱敏</proposal>\n"
            "  </kb_proposals>\n"
            "  <notes>read shared_protocol.md</notes>\n"
            "</agent_response>\n"
        )
        rc, out = run([os.path.join(SCRIPTS, "kb_inbox.py"), "--check-response",
                       "--agent", "requirement-analyst", "--text-file", good, "--root", tmp])
        check(rc == 0, "kb_inbox accepts valid <agent_response>", out.strip())

        rc, out = run([os.path.join(SCRIPTS, "kb_inbox.py"),
                       "--agent", "requirement-analyst", "--text-file", good, "--root", tmp])
        inbox = os.path.join(tmp, "project_workspace", "_kb_inbox.jsonl")
        rows = [json.loads(l) for l in io.open(inbox, encoding="utf-8")] if os.path.isfile(inbox) else []
        check(len(rows) == 2, "kb_inbox appended 2 proposals", "rows=%d" % len(rows))
        check(all("hunter2" not in r["text"] for r in rows), "kb_inbox redacts secrets")
        check(any(r["redacted"] for r in rows), "kb_inbox marks redacted rows")

        rc, out = run([os.path.join(SCRIPTS, "kb_inbox.py"),
                       "--agent", "requirement-analyst", "--text-file", good, "--root", tmp])
        rows2 = [json.loads(l) for l in io.open(inbox, encoding="utf-8")]
        check(len(rows2) == len(rows), "kb_inbox is idempotent", "rows=%d" % len(rows2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def webfetch() -> None:
    g = os.path.join(SCRIPTS, "webfetch_guard.py")
    rc, out = run([g, "--url", "https://code.claude.com/docs/en/hooks"])
    check(rc == 0, "webfetch allows official hooks page", out.strip())

    rc, out = run([g, "--url", "https://code.claude.com/docs/en/hooks?x=1"])
    check(rc == 1, "webfetch denies query string", out.strip()[:80])

    rc, out = run([g, "--url", "https://example.com/docs/en/hooks"])
    check(rc == 1, "webfetch denies non-allowlisted host", out.strip()[:80])

    rc, out = run([g, "--search", "anything"])
    check(rc == 1, "webfetch denies WebSearch", out.strip()[:80])

    tmp = tempfile.mkdtemp(prefix="sdlc_cite_")
    try:
        doc = os.path.join(tmp, "out.md")
        io.open(doc, "w", encoding="utf-8").write(
            "见 [WEB: https://code.claude.com/docs/en/skills, 2026-10-23] 与 https://example.com/x")
        rc, out = run([g, "--check-citations", doc])
        check(rc == 1, "citation check flags off-allowlist URL", out.strip()[:80])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def xml_guard() -> None:
    # Prove the documented XML validation command works on a good file and fails on a bad one.
    tmp = tempfile.mkdtemp(prefix="sdlc_xml_")
    try:
        good = os.path.join(tmp, "good.xml")
        io.open(good, "w", encoding="utf-8").write("<a><b>1</b></a>")
        bad = os.path.join(tmp, "bad.xml")
        io.open(bad, "w", encoding="utf-8").write("<a><b>1</a>")
        for path, want in ((good, True), (bad, False)):
            try:
                ET.parse(path)
                ok = True
            except Exception:
                ok = False
            check(ok is want, "xml guard on %s" % os.path.basename(path))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("== structural ==")
    structural()
    print("== preflight ==")
    preflight()
    print("== kb_inbox ==")
    kb_inbox()
    print("== webfetch guard ==")
    webfetch()
    print("== xml guard ==")
    xml_guard()

    failed = [label for ok, label in results if not ok]
    print("\nSUITE_SELFTEST total=%d passed=%d failed=%d" % (len(results), len(results) - len(failed), len(failed)))
    if failed:
        for label in failed:
            print("  FAILED: " + label)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
