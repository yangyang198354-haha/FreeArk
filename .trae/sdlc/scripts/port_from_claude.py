#!/usr/bin/env python3
"""Port the Claude SDLC agent suite (.claude/agents/*.md) into Trae skills.

Design rules:
- NEVER modify .claude/** (source of truth stays untouched).
- Preserve the full body of every agent definition; only apply platform mappings.
- Emit `.trae/skills/sdlc-*/SKILL.md` with a Trae header block + converted body.

Usage:
    python .trae/sdlc/scripts/port_from_claude.py            # write
    python .trae/sdlc/scripts/port_from_claude.py --check    # report only
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC = os.path.join(ROOT, ".claude", "agents")
DST = os.path.join(ROOT, ".trae", "skills")
PACKS = os.path.join(ROOT, ".trae", "agent-packs")
RUNTIME = os.path.join(ROOT, ".trae", "sdlc")

# Source suite version (kept in one place; bump when .claude/agents changes).
SUITE_VERSION = "v3.7"

# Single-file pack output order (kept compatible with the previous port names).
PACK_ORDER = [
    ("pm-orchestrator", "01-pm-orchestrator"),
    ("requirement-analyst", "02-requirement-analyst"),
    ("system-architect", "03-system-architect"),
    ("software-developer", "04-software-developer"),
    ("test-engineer", "05-test-engineer"),
    ("devops-engineer", "06-devops-engineer"),
    ("agent-builder", "07-agent-builder"),
    ("kb-curator", "08-kb-curator"),
]

# Claude tool -> Trae tool (only platform-specific names change).
TRAE_TOOLS = {"Agent": "Skill", "Bash": "Shell"}


def trae_tools(raw: str) -> str:
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return ", ".join(TRAE_TOOLS.get(n, n) for n in names)

# claude agent file stem -> trae skill dir
AGENT_MAP = {
    "pm-orchestrator": "sdlc-orchestrator",
    "requirement-analyst": "sdlc-requirement-analyst",
    "system-architect": "sdlc-system-architect",
    "software-developer": "sdlc-software-developer",
    "test-engineer": "sdlc-test-engineer",
    "devops-engineer": "sdlc-devops-engineer",
    "kb-curator": "sdlc-kb-curator",
    "agent-builder": "sdlc-agent-builder",
    "shared_protocol": "sdlc-shared-protocol",
}

MECHANISM_NOTE = {
    "sdlc-orchestrator": [
        "本技能是**主控入口**：以 `Skill` 工具在本会话加载后，你即 PM，直接与用户对话。",
        "子代理调用：原套件用 Claude Code 的 `Agent` 工具按角色派生子会话；"
        "TRAE 中改为**串行调用对应 `sdlc-*` skill**（一次只加载一个，行为等价）。",
        "TRAE 的 skill 与本会话**共享上下文窗口**：子代理返回后，PM 必须立即执行"
        "「落盘校验 + 门控评审」，不要依赖独立上下文。",
        "Hook 等效：原 `PreToolUse(Agent)` / `SubagentStop` 由本技能内的**强制前置检查**与"
        "`scripts/` 下的脚本承担，见共享协议 §N。",
    ],
    "sdlc-shared-protocol": [
        "本技能为**只读参考协议**，不直接执行任务。",
        "协议中的 `Agent` 工具子代理调用，在 TRAE 中对应「调用 `sdlc-*` skill」。",
        "Hook 迁移到脚本：见本文件 §N（TRAE 运行适配）。",
    ],
}

GENERIC_NOTE = [
    "调用：以 `Skill` 工具调用本技能，名称 = `{skill}`。",
    "机制映射：Claude Code `Agent` 子代理 → TRAE `sdlc-*` skill；`Bash` 工具 → `Shell` 工具。",
    "项目记忆：原套件由运行时**自动注入** `MEMORY.md`；TRAE **不会自动注入**，"
    "本技能第一步必须**显式 Read** `.trae/sdlc/agent-memory/{slug}/MEMORY.md`（不存在则视为空）。",
    "经验收件箱：原 `SubagentStop` hook 自动收集；TRAE 由 PM 在每次子代理返回后运行 "
    "`python .trae/sdlc/scripts/kb_inbox.py` 强制补记。",
]

# Ordered replacements (longest / most specific first).
REPLACEMENTS = [
    (r"\.claude/agents/shared_protocol\.md", ".trae/skills/sdlc-shared-protocol/SKILL.md"),
    (r"\.claude/agents/project_profile\.md", ".trae/sdlc/project_profile.md"),
    (r"\.claude/agents/knowledge_base/generic/", ".trae/sdlc/knowledge_base/generic/"),
    (r"\.claude/agents/knowledge_base/", ".trae/sdlc/knowledge_base/"),
    (r"\.claude/agents/templates/", ".trae/skills/sdlc-agent-builder/templates/"),
    (r"\.claude/agent-memory/", ".trae/sdlc/agent-memory/"),
    (r"\.claude/hooks/", ".trae/sdlc/scripts/"),
    (r"\.claude/agents/", ".trae/skills/"),
    (r"claude --agent pm-orchestrator", "Skill: sdlc-orchestrator"),
    (r"claude --agent kb-curator", "Skill: sdlc-kb-curator"),
    (r"claude --agent agent-builder", "Skill: sdlc-agent-builder"),
    (r"claude --agent ", "Skill: sdlc-"),
    (r"`templates/project_profile\.template\.md`", "`.trae/sdlc/project_profile.template.md`"),
    (r"`MEMORY\.md` 会自动注入，无需 Read", "`MEMORY.md` 需显式 Read"),
    (r"自动注入", "不会自动注入，必须显式 Read"),
    (r"subagent_type", "技能名"),
    (r"`技能名` 取下表名称", "技能名取下表"),
    (r"`` `技能名` 取下表名称 ``", "技能名取下表"),
    (r"\| A \| `requirement-analyst` \|", "| A | `sdlc-requirement-analyst` |"),
    (r"\| B \| `system-architect` \|", "| B | `sdlc-system-architect` |"),
    (r"\| C \| `software-developer` \|", "| C | `sdlc-software-developer` |"),
    (r"\| D \| `test-engineer` \|", "| D | `sdlc-test-engineer` |"),
    (r"\| E1 / E2 \| `devops-engineer` \|", "| E1 / E2 | `sdlc-devops-engineer` |"),
    (r"\| Z \| `kb-curator` \|", "| Z | `sdlc-kb-curator` |"),
    (r"写 `\.claude/` 失败时", "写 `.trae/sdlc/` 失败时"),
    (r"写 `\.claude/` 失败（无人值守常见）", "写 `.trae/sdlc/` 失败（无人值守常见）"),
    (r"无人值守时 `\.claude/` 可能不可写", "无人值守时 `.trae/sdlc/` 可能不可写"),
    (r"Claude Code 的子代理虽然可以再调用子代理（默认最多三层），但子代理无法与用户对话",
     "TRAE 中技能由主会话**串行**加载（无独立子代理），技能之间共享上下文"),
    (r"、`\.claude/skills/`。", "、`.claude/skills/`（只读参考）、`.trae/skills/`。"),
    (r"Agent 工具", "Skill 工具"),
    (r"已不会自动注入", "不会自动注入"),
    (r"`?date -Iseconds`?", "Get-Date -Format o（Windows）或 date -Iseconds（Linux）"),
    (r"`\.trae/sdlc/scripts/sdlc_pre_agent\.py`（PreToolUse 钩子）会在当前目录不是仓库根时拒绝 Agent 调用，拒绝原因里给出仓库根的绝对路径，照做后重试。",
     "`python .trae/sdlc/scripts/sdlc_preflight.py --check-cwd`（TRAE 等效检查）会在当前目录不是仓库根时返回非 0，并给出仓库根的绝对路径；照做后重试。"),
    (r"Claude Code 按调用子代理时的当前目录创建", "TRAE 中记忆目录固定为"),
    (r"子代理结束时 SubagentStop hook 会自动把",
     "TRAE 无 SubagentStop hook：每次子技能返回后，你**必须**运行 `python .trae/sdlc/scripts/kb_inbox.py --agent <agent> --text-file <reply>` 把"),
    (r"\bBash\b", "Shell"),
    (r"\bpython3\b", "python"),
    (r"\.claude/settings\*\.json", ".trae/sdlc/suite_config.md"),
]

RESIDUAL = re.compile(r"\.claude/(agents|hooks|agent-memory)")

TEMPLATE_ADDENDUM = (
    "> **TRAE 移植说明**：本文件是 `.claude/agents/templates/agent_builder_templates.md` 的只读副本。\n"
    "> 其中 T1–T4 面向 **Claude Code** 目标；生成 **TRAE** 目标时改用\n"
    "> `sdlc-agent-builder/SKILL.md` §9「Trae 目标形态」与共享协议 §N-6。\n"
    "> 本副本不修改 `.claude/**`。\n\n"
)


def sync_runtime() -> list[str]:
    """Mirror version-coupled runtime assets (generic KB + templates)."""
    msgs: list[str] = []

    src_kb = os.path.join(SRC, "knowledge_base", "generic")
    dst_kb = os.path.join(RUNTIME, "knowledge_base", "generic")
    os.makedirs(dst_kb, exist_ok=True)
    for name in sorted(os.listdir(src_kb)):
        if not name.endswith(".md"):
            continue
        shutil.copyfile(os.path.join(src_kb, name), os.path.join(dst_kb, name))
        msgs.append(f"{'KB':22s} -> {os.path.relpath(os.path.join(dst_kb, name), ROOT)}")

    src_readme = os.path.join(SRC, "knowledge_base", "README.md")
    if os.path.isfile(src_readme):
        shutil.copyfile(src_readme, os.path.join(RUNTIME, "knowledge_base", "README.md"))

    src_tpl = os.path.join(SRC, "templates", "agent_builder_templates.md")
    dst_tpl = os.path.join(DST, "sdlc-agent-builder", "templates", "agent_builder_templates.md")
    if os.path.isfile(src_tpl):
        text = read(src_tpl)
        first, _, rest = text.partition("\n")
        os.makedirs(os.path.dirname(dst_tpl), exist_ok=True)
        with io.open(dst_tpl, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(first + "\n\n" + TEMPLATE_ADDENDUM + rest.lstrip("\n"))
        msgs.append(f"{'TEMPLATE':22s} -> {os.path.relpath(dst_tpl, ROOT)}")

    return msgs

# Appended verbatim after the converted body. Keeps the port reproducible:
# re-running this script never loses the TRAE adaptation layer.
POSTAMBLE = {
    "sdlc-shared-protocol": """
## N. TRAE 运行适配（本移植新增，与 §A–§M 同等效力）

### N-1. 调用机制
- 主控 = 主会话加载 `Skill: sdlc-orchestrator`；子代理 = **串行**加载 `sdlc-<role>` skill，一次只加载一个。
- TRAE 的技能与主会话**共享上下文**：子技能返回后，PM 必须在同一轮内完成 `<agent_response>` 校验、落盘核对与门控评审。
- 子技能不等待回复：返回 `CLARIFICATION_NEEDED` 即结束，PM 取得答案后带答案重新加载该技能。

### N-2. Hook 等效（强制命令）
| 原 Claude hook | TRAE 等效命令 | 强制时机 |
|---|---|---|
| PreToolUse(Agent) | `python .trae/sdlc/scripts/sdlc_preflight.py --check-cwd` | 每次加载子技能前；非 0 禁止调用 |
| SubagentStop（完整性） | `python .trae/sdlc/scripts/kb_inbox.py --check-response --text-file <reply>` | 每次子技能返回后；缺 `<agent_response>`/`<invocation_id>`/`<status>` 视为 FAILURE |
| SubagentStop（收件箱） | `python .trae/sdlc/scripts/kb_inbox.py --agent <agent> --text-file <reply>` | 同上；幂等写入 `project_workspace/_kb_inbox.jsonl` |
| PreToolUse(WebFetch/WebSearch) | `python .trae/sdlc/scripts/webfetch_guard.py --url <u>` / `--search` / `--check-citations <file>` | agent-builder 联网前与产出后 |

`<reply>` = 子技能最终回复的原文落盘副本（建议 `project_workspace/.hook_state/last_reply_<agent>.md`）。

### N-3. 记忆
- TRAE **不会自动注入** `MEMORY.md`：每个技能第 1 步必须显式 Read `.trae/sdlc/agent-memory/{agent}/MEMORY.md`（不存在视为空），并在 `<notes>` 中列出。
- 写入规则同 §M-2；kb-curator 维护「已验证」区，其他 agent 仅可追加「待验证」区。

### N-4. 时间与 XML
- 时间：Windows 用 `Get-Date -Format o`，Linux/macOS 用 `date -Iseconds`；禁止占位值。
- `phase_status.md` 写盘后必须校验：`python -c "import sys,xml.etree.ElementTree as E;E.parse(sys.argv[1])" <path>`；报错立即修正转义。

### N-5. 平台边界
- `.claude/**` 是**只读源套件**：任何 agent 不得修改（agent-builder 也不例外）。
- agent-builder 的 Claude Code 文档白名单仅用于**评审/生成 Claude 目标**；生成 Trae 目标时按 N-6 规范。

### N-6. Trae 目标规范（agent-builder 生成 Trae 技能时）
- 路径：`.trae/skills/<name>/SKILL.md`；frontmatter 仅 `name`（必须等于目录名）与 `description`。
- 工具：`Shell` 取代 `Bash`；子代理用 `Skill` 取代 `Agent`。
- 记忆：显式 Read，不假定自动注入。
- Hook 语义：用 N-2 的脚本，并在技能中写明「必须在何时运行」。
- 不得出现 `temperature` 等平台不存在的参数。
""",
    "sdlc-orchestrator": """
## 10. TRAE 强制钩子等效（与 §4 同等效力）

> TRAE 没有 Claude Code 的 hook 运行时，以下三条**不可省略**；缺失即视为流程违规（门控记 MINOR；若因此漏掉 `<agent_response>` 校验则记 FAIL）。

1. **调用前**：`python .trae/sdlc/scripts/sdlc_preflight.py --check-cwd`（返回非 0 → 禁止调用，先回到仓库根）。
2. **返回后（完整性）**：把子技能最终回复落盘到 `project_workspace/.hook_state/last_reply_<agent>.md`，运行
   `python .trae/sdlc/scripts/kb_inbox.py --check-response --text-file <该文件>`；返回 3 → 视为 FAILURE
   （缺 `<agent_response>` / `<invocation_id>` / `<status>`），要求补齐后重新返回。
3. **返回后（收件箱）**：`python .trae/sdlc/scripts/kb_inbox.py --agent <agent> --text-file <该文件>`（幂等；无 proposal 时打印 unchanged）。

补充：
- agent-builder 联网前必须 `python .trae/sdlc/scripts/webfetch_guard.py --url <url>`（或 `--search`），产出后 `--check-citations`。
- 子技能开始时必须显式 Read 自己的 `MEMORY.md`（TRAE 不自动注入）；门控时检查 `<notes>` 是否列出。

### 10.1 阶段组字面量映射（供脚本与门控核对）

| 简写 | 协议阶段组 | 角色技能 |
|---|---|---|
| A | GROUP_A | `sdlc-requirement-analyst` |
| B | GROUP_B | `sdlc-system-architect` |
| C | GROUP_C | `sdlc-software-developer` |
| D | GROUP_D | `sdlc-test-engineer` |
| E1 | GROUP_E1 | `sdlc-devops-engineer` |
| E2 | GROUP_E2 | `sdlc-devops-engineer` |
| Z | GROUP_Z | `sdlc-kb-curator` |

流程描述中的 A/B/C/D/E1 简写**等价于**上表的 `GROUP_*` 字面量；`phase_status.md` 与 `gate_review` 一律使用 `GROUP_*` 形式。
""",
    "sdlc-agent-builder": """
## 9. Trae 目标形态（本移植新增）

当 `WRITE_TARGET` 指向 `.trae/skills/...` 时，按以下规范评审/生成，而不是 Claude 规范：

| 维度 | Trae 规范 |
|---|---|
| 路径 | `.trae/skills/<name>/SKILL.md`（目录名 = frontmatter `name`） |
| frontmatter | 仅 `name` + `description`；不写 `tools`/`model`/`color`/`memory`（Trae 无此语义） |
| 工具 | `Shell` 代替 `Bash`；子代理用 `Skill` 代替 `Agent` |
| 记忆 | 显式 Read `.trae/sdlc/agent-memory/{agent}/MEMORY.md`；不得声称「自动注入」 |
| Hook | 用 `.trae/sdlc/scripts/` 的脚本，并写明强制时机（对应 shared_protocol §N-2） |
| 共享协议引用 | `.trae/skills/sdlc-shared-protocol/SKILL.md` |
| 禁止 | 修改 `.claude/**`；出现 `temperature` 等平台不存在参数；声称 Trae 会做自动注入或 hook 拦截 |

评审 SUITE 类比：目标在 `.trae/skills/` 下且引用 `.trae/skills/sdlc-shared-protocol/SKILL.md` 即视为本套件成员；其引用章节覆盖的检查项视为已满足，改查引用是否准确。
""",
}


def read(path: str) -> str:
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, body


def yaml_scalar(text: str) -> str:
    """Quote a YAML scalar so ASCII ':' etc. cannot break frontmatter parsing."""
    needs = any(ch in text for ch in ":#{}[],&*?|->=!%@`\"'") or text != text.strip()
    if needs:
        return "'" + text.replace("'", "''") + "'"
    return text


def convert(slug: str, skill: str, meta: dict[str, str], body: str) -> str:
    for pattern, repl in REPLACEMENTS:
        body = re.sub(pattern, repl, body)

    tools = meta.get("tools", "")
    if skill == "sdlc-shared-protocol":
        description = (
            "SDLC 智能体套件共享协议（TRAE 版）：工作区与写权限、强制文件头、12 阶段与阶段组、"
            "状态码、调用与响应格式、门控评审与通过标准、测试度量、安全合规、记忆与知识蒸馏、"
            "TRAE 运行适配（hook/记忆/时间命令）。被 sdlc-orchestrator 及各 sdlc-* 角色技能引用。"
        )
    else:
        description = meta.get("description", "").strip()
        for pattern, repl in REPLACEMENTS:
            description = re.sub(pattern, repl, description)
        description = description[:1800]

    lines = ["---", f"name: {skill}", f"description: {yaml_scalar(description)}", "---", ""]

    if skill in MECHANISM_NOTE:
        lines.append(f"> **TRAE 运行说明（复刻自 `.claude/agents/{slug}.md`，套件 {SUITE_VERSION}）**")
        for item in MECHANISM_NOTE:
            lines.append(f"> - {item}")
        if tools:
            lines.append(f"> - 工具需求（Trae）：{trae_tools(tools)}")
        lines.append("")
    else:
        lines.append(f"> **TRAE 运行说明（复刻自 `.claude/agents/{slug}.md`，套件 {SUITE_VERSION}）**")
        for item in GENERIC_NOTE:
            lines.append("> - " + item.format(skill=skill, slug=slug))
        if tools:
            lines.append(f"> - 工具需求（Trae）：{trae_tools(tools)}")
        lines.append("> - 通用知识库：`.trae/sdlc/knowledge_base/generic/{0}.md`（必读）".format(slug))
        lines.append("")

    body = body.rstrip()
    if skill in POSTAMBLE:
        body += "\n" + POSTAMBLE[skill].rstrip() + "\n"
    return "\n".join(lines) + body + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    report = []
    generated: list[tuple[str, str, str]] = []
    for slug, skill in AGENT_MAP.items():
        src = os.path.join(SRC, slug + ".md")
        if not os.path.isfile(src):
            report.append(f"MISSING source: {src}")
            continue
        meta, body = split_frontmatter(read(src))
        converted_body = body
        for pattern, repl in REPLACEMENTS:
            converted_body = re.sub(pattern, repl, converted_body)
        out = convert(slug, skill, meta, body)
        target = os.path.join(DST, skill, "SKILL.md")

        residuals = RESIDUAL.findall(converted_body)
        report.append(
            f"{slug:22s} -> {os.path.relpath(target, ROOT):55s} "
            f"body_residual={len(residuals)} lines={out.count(chr(10)) + 1}"
        )
        if not args.check:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with io.open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(out)
        generated.append((slug, skill, out))

    # Single-file packs: same body as the skill (parity is asserted by tests/agents).
    pack_by_slug = dict(PACK_ORDER)
    for slug, skill, out in generated:
        pack_name = pack_by_slug.get(slug)
        if not pack_name:
            continue
        body = split_frontmatter(out)[1].rstrip()
        pack_text = (
            f"<!-- agent-pack: {skill} | source: .claude/agents/{slug}.md@{SUITE_VERSION} | "
            f"generator: .trae/sdlc/scripts/port_from_claude.py -->\n"
            f"# Agent Pack — {skill}\n\n"
            f"> 单文件注册包：正文与 `.trae/skills/{skill}/SKILL.md` **逐字一致**（不含 frontmatter）。\n"
            f"> 用法：在不支持 skills 的会话中，把本文件全文作为该角色的系统提示；\n"
            f"> 在 TRAE 中优先直接加载 `Skill: {skill}`。\n\n"
            f"{body}\n"
        )
        pack_path = os.path.join(PACKS, pack_name + ".md")
        report.append(
            f"{'PACK':22s} -> {os.path.relpath(pack_path, ROOT):55s} "
            f"lines={pack_text.count(chr(10)) + 1}"
        )
        if not args.check:
            os.makedirs(PACKS, exist_ok=True)
            with io.open(pack_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(pack_text)

    if not args.check:
        os.makedirs(PACKS, exist_ok=True)
        readme = (
            f"# TRAE 单文件注册包（SDLC Agent Suite {SUITE_VERSION}）\n\n"
            "> 由 `.trae/sdlc/scripts/port_from_claude.py` 从 `.claude/agents/*.md` 生成。\n"
            "> 每个 pack 的正文与对应 `.trae/skills/<skill>/SKILL.md` 的正文**逐字一致**（不含 frontmatter），\n"
            "> 契约测试 `tests/agents/test_sdlc_suite_contract.py` 会断言该一致性。\n"
            "> 源套件 `.claude/**` 保持只读，不被本生成器修改。\n\n"
            "| Pack | Skill | 用途 |\n|---|---|---|\n"
            + "".join(
                f"| `{name}.md` | `{AGENT_MAP[slug]}` | {AGENT_MAP[slug]} 的单文件提示词 |\n"
                for slug, name in PACK_ORDER
            )
            + "\n## 使用方式\n\n"
            "1. **TRAE 会话**：优先 `Skill: sdlc-*`（技能会加载运行时脚本、记忆与知识库路径）。\n"
            "2. **无 skills 的平台**：把对应 pack 全文作为该角色的系统提示；仍需遵守共享协议（pack 内已含 §N 适配）。\n"
            "3. **不要在 pack 上手改**：重跑生成器即可同步；需要改内容请改 `.claude/agents/*.md` 后重新生成。\n"
        )
        with io.open(os.path.join(PACKS, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(readme)

    if not args.check:
        report.extend(sync_runtime())

    print("\n".join(report))
    bad = [r for r in report if "body_residual=" in r and "body_residual=0" not in r]
    if bad:
        print("\nWARNING: residual .claude references remain in:")
        for row in bad:
            print("  " + row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
