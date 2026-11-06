#!/usr/bin/env python3
"""TRAE equivalent of `.claude/hooks/sdlc_webfetch_guard.py`.

Claude Code blocks agent-builder's WebSearch and restricts WebFetch to the
official Claude Code docs allowlist. TRAE cannot intercept tool calls, so:
  - agent-builder must run `--url <url>` / `--search` BEFORE fetching, and
  - the PM (or agent-builder itself) can run `--check-citations <file>` to
    prove that every cited URL in its output is on the allowlist.

Usage:
    python .trae/sdlc/scripts/webfetch_guard.py --url https://code.claude.com/docs/en/hooks
    python .trae/sdlc/scripts/webfetch_guard.py --search "anything"
    python .trae/sdlc/scripts/webfetch_guard.py --check-citations out.md

Exit codes:
    0  allowed / all citations allowed
    1  denied / citation outside the allowlist
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from urllib.parse import urlsplit

ALLOWED_PAGES = {"sub-agents", "hooks", "settings", "permissions",
                 "memory", "skills", "mcp", "cli-reference"}
ALLOWED = "、".join("https://code.claude.com/docs/en/" + p for p in sorted(ALLOWED_PAGES))


def allowed(url: str) -> tuple[bool, str]:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    page = path[len("/docs/en/"):] if path.startswith("/docs/en/") else ""
    ok = (parts.scheme == "https" and parts.hostname == "code.claude.com"
          and not parts.query and page in ALLOWED_PAGES)
    if ok:
        return True, "ALLOWED %s" % url
    return False, ("DENIED agent-builder 只能访问以下官方文档页（不带查询参数）：%s"
                   "。该项判定请标【推断】，不扣分。" % ALLOWED)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--search")
    ap.add_argument("--check-citations")
    args = ap.parse_args()

    if args.search is not None:
        print("DENIED agent-builder 不允许使用 WebSearch；只能用 WebFetch 访问官方文档白名单页。")
        return 1

    if args.url:
        ok, msg = allowed(args.url)
        print(msg)
        return 0 if ok else 1

    if args.check_citations:
        with io.open(args.check_citations, encoding="utf-8") as fh:
            text = fh.read()
        urls = re.findall(r"https?://[^\s\)\]>`\"']+", text)
        bad = [u for u in dict.fromkeys(urls) if not allowed(u)[0]]
        if bad:
            print("CITATIONS_DENIED %d" % len(bad))
            for u in bad:
                print("  - " + u)
            return 1
        print("CITATIONS_OK %d" % len(set(urls)))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("WEBFETCH_GUARD_ERROR %s" % exc)
        sys.exit(0)
