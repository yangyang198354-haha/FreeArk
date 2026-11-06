#!/usr/bin/env python3
"""TRAE equivalent of `.claude/hooks/sdlc_subagent_stop.py`.

In Claude Code a SubagentStop hook (a) blocks once when the final message lacks
`<agent_response>` and (b) appends every `<kb_proposals><proposal>` to
`project_workspace/_kb_inbox.jsonl` with secrets redacted. TRAE has no hook
runtime, so the PM runs this right after each subagent skill returns.

Usage:
    python .trae/sdlc/scripts/kb_inbox.py --check-response --text-file reply.txt
    python .trae/sdlc/scripts/kb_inbox.py --agent requirement-analyst \
        --text-file reply.txt [--root .] [--docs docs/sdlc/demo]

Exit codes:
    0  response OK (and, if proposals, appended/idempotent)
    3  response missing <agent_response>, <invocation_id> or <status> (PM must re-ask)
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys

SECRET = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|(?i:password|passwd|secret|token)\s*[=:]\s*\S+)"
)


def read_text(path: str | None) -> str:
    if path:
        with io.open(path, encoding="utf-8") as fh:
            return fh.read()
    return sys.stdin.read()


def find(tag: str, text: str) -> str:
    m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
    return m.group(1).strip() if m else ""


def check_response(text: str) -> tuple[bool, str]:
    if "<agent_response>" not in text:
        return False, "缺少 <agent_response> 块（共享协议 §E）"
    inv = find("invocation_id", text)
    status = find("status", text)
    if not inv:
        return False, "<agent_response> 缺少 <invocation_id>"
    if not status:
        return False, "<agent_response> 缺少 <status>"
    if status not in {"SUCCESS", "PARTIAL_SUCCESS", "FAILURE", "BLOCKED", "CLARIFICATION_NEEDED"}:
        return False, "<status> 非法值：%s" % status
    return True, "OK invocation_id=%s status=%s" % (inv, status)


def proposals(text: str, agent: str, invocation: str) -> list[dict]:
    block = re.search(r"<kb_proposals>(.*?)</kb_proposals>", text, re.S)
    if not block:
        return []
    rows = []
    for i, m in enumerate(re.finditer(r"<proposal([^>]*)>(.*?)</proposal>", block.group(1), re.S), 1):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        body = " ".join(m.group(2).split())
        if not body:
            continue
        redacted = bool(SECRET.search(body) or SECRET.search(attrs.get("evidence", "")))
        rows.append({
            "id": "%s-%d" % (invocation or hashlib.sha1(body.encode()).hexdigest()[:12], i),
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "agent": agent,
            "invocation_id": invocation,
            "scope": attrs.get("scope", ""),
            "evidence": SECRET.sub("[REDACTED]", attrs.get("evidence", "")),
            "text": SECRET.sub("[REDACTED]", body),
            "redacted": redacted,
            "source": "pm",
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="unknown")
    ap.add_argument("--text-file")
    ap.add_argument("--root", default=".")
    ap.add_argument("--planning-dir", default="project_workspace")
    ap.add_argument("--check-response", action="store_true")
    args = ap.parse_args()

    text = read_text(args.text_file)
    ok, msg = check_response(text)
    print(("RESPONSE_OK %s" if ok else "RESPONSE_INVALID %s") % msg)
    if args.check_response:
        # Validation mode is READ-ONLY: never touch the inbox here, so that
        # `--check-response` alone cannot create rows with agent=unknown.
        return 0 if ok else 3
    if not ok:
        return 0

    inv = find("invocation_id", text)
    rows = proposals(text, args.agent, inv)
    if not rows:
        print("KB_INBOX unchanged (no <kb_proposals>)")
        return 0

    target_dir = os.path.join(os.path.abspath(args.root), args.planning_dir)
    os.makedirs(os.path.join(target_dir, ".hook_state"), exist_ok=True)
    inbox = os.path.join(target_dir, "_kb_inbox.jsonl")

    existing = set()
    if os.path.isfile(inbox):
        with io.open(inbox, encoding="utf-8") as fh:
            for line in fh:
                try:
                    existing.add(json.loads(line).get("id"))
                except ValueError:
                    continue

    written = 0
    with io.open(inbox, "a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if row["id"] in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    print("KB_INBOX appended=%d total_proposals=%d path=%s" % (written, len(rows), inbox))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the agent run
        print("KB_INBOX_ERROR %s" % exc)
        sys.exit(0)
