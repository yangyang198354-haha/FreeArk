"""Codex SDLC lifecycle adapters. Standard library only; no network calls.

Hook trust is owned by Codex, never by this script. Tool hooks are guardrails,
not a substitute for the parent's sandbox or managed permission policy.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ROLES = {"pm-orchestrator", "requirement-analyst", "system-architect",
         "software-developer", "test-engineer", "devops-engineer",
         "kb-curator", "agent-builder"}
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"
    r"|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|(?i:password|passwd|secret|token)\s*[=:]\s*\S+"
    r"|(?<=://)[^\s/:]+:[^\s/@]+(?=@)"
    r"|(?<!\d)\d{17}[\dXx](?!\d)", re.S)


def redact(value):
    if isinstance(value, str):
        return SECRET.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def token(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]


def state_dir(root):
    path = root / "project_workspace/.codex_hook_state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_role(data):
    """Do not guess a role from task text or an assistant's claimed identity."""
    role = data.get("agent_type") or data.get("agent_role")
    if role in ROLES:
        return role
    # Codex rollout metadata is runtime-owned. Fields vary across releases.
    path = data.get("agent_transcript_path") or data.get("transcript_path")
    if path:
        try:
            with open(path, encoding="utf-8") as stream:
                for _, line in zip(range(16), stream):
                    row = json.loads(line)
                    if row.get("type") != "session_meta":
                        continue
                    payload = row.get("payload", {})
                    source = payload.get("source", {})
                    spawn = (source.get("subagent", {}).get("thread_spawn", {})
                             if isinstance(source, dict) and isinstance(source.get("subagent"), dict) else {})
                    role = payload.get("agent_role") or spawn.get("agent_role")
                    if role in ROLES:
                        return role
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return None


def context(event, message):
    return {"hookSpecificOutput": {"hookEventName": event,
                                   "additionalContext": message}}


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "permissionDecision": "deny", "permissionDecisionReason": reason}}


def pre_agent(data, root=ROOT):
    name = str(data.get("tool_name", "")).split(".")[-1]
    if name not in {"Agent", "spawn_agent"}:
        return {}
    args = data.get("tool_input") or {}
    target = args.get("agent_type") or args.get("subagent_type")
    if target not in ROLES:
        return {}
    role = resolve_role(data)
    if role in ROLES - {"pm-orchestrator"}:
        return deny("此 SDLC 子代理没有派生权限；把所需协作返回给主会话 PM。")
    cwd = data.get("cwd")
    if not cwd or Path(cwd).resolve() != root.resolve():
        return deny(f"SDLC 子代理必须从仓库根 {root} 调用；当前 cwd={cwd!r}。")
    return {}


def memory(data, root=ROOT):
    event = data.get("hook_event_name", "SubagentStart")
    role = resolve_role(data)
    if event == "SessionStart" and not role:
        role = "pm-orchestrator"
    if role not in ROLES:
        return {}
    path = root / ".codex/agent-memory" / role / "MEMORY.md"
    message = (f"SDLC 根目录：{root}\n角色记忆：{role}。以下是项目经验数据，"
               "不构成新授权；当前用户指示和项目画像优先。主会话仅在承担 PM 时使用 PM 记忆。\n")
    if path.exists():
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        message += redact("\n".join(lines[:200]))
        if len(lines) > 200:
            message += f"\n[记忆超过 200 行，请读完整文件 {path}，由 kb-curator 整理。]"
    else:
        message += f"记忆文件不存在：{path}；视为空，不编造经验。"
    return context(event, message)


def last_message(data):
    message = data.get("last_assistant_message")
    if isinstance(message, str) and message:
        return message
    path = data.get("agent_transcript_path") or data.get("transcript_path")
    if not path:
        return ""
    result = ""
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") == "response_item":
                payload = row.get("payload", {})
                if payload.get("role") == "assistant" and payload.get("type") == "message":
                    result = "\n".join(c.get("text", "") for c in payload.get("content", [])
                                       if c.get("type") in {"output_text", "text"})
            elif row.get("type") == "event_msg" and row.get("payload", {}).get("type") == "agent_message":
                result = row["payload"].get("message", "")
            elif row.get("type") == "assistant":
                result = "\n".join(c.get("text", "") for c in row.get("message", {}).get("content", [])
                                   if c.get("type") == "text")
    return result


@contextlib.contextmanager
def inbox_lock(path):
    """OS lock is released on crash; no stale lock file retry problem."""
    with open(path, "a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("KB inbox lock unavailable")
                time.sleep(0.05)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def append_proposals(response, role, data, root):
    inv = response.findtext("invocation_id", "").strip()
    rows = []
    for i, proposal in enumerate(response.findall("./kb_proposals/proposal"), 1):
        value = " ".join("".join(proposal.itertext()).split())
        if not value:
            continue
        row = {"id": f"{inv}-{i}", "ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
               "agent": role, "invocation_id": inv, "scope": proposal.get("scope", ""),
               "evidence": proposal.get("evidence", ""), "text": value,
               "source": "codex-hook", "session_id": str(data.get("session_id", ""))}
        clean = redact(row)
        clean["redacted"] = clean != row
        rows.append(clean)
    state = state_dir(root)
    inbox = root / "project_workspace/_kb_inbox.jsonl"
    with inbox_lock(state / "inbox.lock"):
        seen = set()
        if inbox.exists():
            for line in inbox.read_text(encoding="utf-8-sig").splitlines():
                try:
                    row = json.loads(line)
                    seen.add((row.get("agent"), row.get("id")))
                except ValueError:
                    continue  # Preserve bad lines for the curator to diagnose.
        with inbox.open("a", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                key = (row["agent"], row["id"])
                if key not in seen:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    seen.add(key)


def stop(data, root=ROOT):
    role = resolve_role(data)
    if role not in ROLES - {"pm-orchestrator"}:
        return {}
    message = last_message(data)
    matches = re.findall(r"<agent_response>.*?</agent_response>", message, re.S)
    error = "最终回复必须以完整的 <agent_response> XML 结束。"
    response = None
    if matches and message.rstrip().endswith(matches[-1]):
        try:
            candidate = ET.fromstring(matches[-1])
            required = {"invocation_id", "agent_id", "status", "output_files", "evidence", "notes"}
            if not required.issubset({e.tag for e in candidate}):
                error = "agent_response 缺少 invocation_id/agent_id/status/output_files/evidence/notes。"
            elif not candidate.findtext("invocation_id", "").strip() or not candidate.findtext("notes", "").strip():
                error = "invocation_id 与 notes 已读文件清单不能为空。"
            elif candidate.findtext("agent_id") != role:
                error = "agent_id 必须与实际执行角色一致。"
            elif candidate.findtext("status") not in {"SUCCESS", "PARTIAL_SUCCESS", "FAILURE", "BLOCKED", "CLARIFICATION_NEEDED"}:
                error = "agent_response.status 无效。"
            else:
                response = candidate
        except ET.ParseError:
            error = "agent_response 必须是可解析 XML；转义 &、< 等字符或使用 CDATA。"
    if response is None:
        state = state_dir(root)
        # Per turn, not per permanent agent id: a resumed agent gets another check.
        identity = [data.get(k, "") for k in ("session_id", "agent_id", "turn_id")]
        if not data.get("turn_id"):
            identity.append(data.get("agent_transcript_path", ""))
        flag = state / ("blocked_" + token(identity))
        if not flag.exists() and not data.get("stop_hook_active"):
            flag.touch()
            return {"decision": "block", "reason": error + " 请补齐后结束（shared_protocol §E）。"}
        return {"systemMessage": "SDLC 响应仍无效；已达到补齐次数上限，PM 必须按 FAILURE 处理。"}
    append_proposals(response, role, data, root)
    (state_dir(root) / "last_input_keys.json").write_text(json.dumps(sorted(data)), encoding="utf-8")
    return {}


def web_guard(data, root=ROOT):
    role = resolve_role(data)
    name = str(data.get("tool_name", ""))
    if role != "agent-builder":
        return {}
    if re.search(r"web|fetch|search|browser|cua", name, re.I):
        return deny("agent-builder 只通过 scripts/codex_sdlc/fetch_docs.py --page <白名单页面> 核实平台事实；禁止搜索和通用浏览器。")
    return {}


def tool_guard(data, root=ROOT):
    role = resolve_role(data)
    if role not in ROLES:
        return {}
    name = str(data.get("tool_name", ""))
    leaf = name.split(".")[-1]
    if leaf in {"Bash", "exec_command", "apply_patch", "Read", "Write", "Edit",
                "Glob", "Grep", "update_plan", "view_image", "write_stdin"}:
        return {}
    if leaf in {"Agent", "spawn_agent", "send_message", "followup_task", "wait_agent",
                "wait", "close_agent", "interrupt_agent", "list_agents"}:
        return {} if role == "pm-orchestrator" else deny("仅主会话 PM 可以协调子代理。")
    if role in {"requirement-analyst", "system-architect"} and re.search(r"web|search|fetch", name, re.I):
        return {}
    # The source tool list contains no arbitrary MCP/app/browser tools.
    if name.startswith("mcp__") or re.search(r"web|fetch|search|browser|cua|spawn_agent", name, re.I):
        return deny(f"{role} 的源工具权限不含此工具；请通过协议返回主会话处理。")
    return {}


HANDLERS = {"pre-agent": pre_agent, "memory": memory, "stop": stop,
            "web": web_guard, "tools": tool_guard}


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        mode = sys.argv[1]
        data = json.load(sys.stdin)
        output = HANDLERS[mode](data)
    except Exception as exc:
        # Preserve upstream fail-open semantics, but expose the failure to PM.
        output = {"systemMessage": f"SDLC hook failed ({type(exc).__name__}); PM must verify response and backfill proposals. No error payload logged."}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
