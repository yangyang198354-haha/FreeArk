#!/usr/bin/env python3
"""SDLC Agent Suite → Trae 技能套件迁移脚本。

源（Claude→Codex 迁移产物，作为单一事实源）：
  .codex/agents/<role>.toml           8 个角色定义（name/description/developer_instructions）
  .codex/sdlc/*.md                    共享协议、项目画像、知识库、模板
  .codex/agent-memory/<role>/MEMORY.md 各角色项目记忆

目标（Trae 原生可发现）：
  .agents/skills/sdlc-<role>/SKILL.md  9 个技能（PM + 8 角色）
  .agents/sdlc/                        共享参考文件 + 记忆（运行时读取）

设计要点：
  1. Trae 通过 .agents/skills/*/SKILL.md 的 frontmatter(name/description) 发现技能；
     子代理（general-purpose）具备 Skill 工具，可自行加载角色技能。
  2. 角色正文做路径重写（.codex/ → .agents/）+ 工具名映射（Codex→Trae）。
  3. 记忆复制一份到 .agents/sdlc/memory/，Trae 侧独立演进（不回写 .codex）。
  4. 幂等：重复运行覆盖同一批生成文件；--check 只比对不写盘。

用法：
  python scripts/trae_sdlc/migrate.py build     # 生成到 .agents/
  python scripts/trae_sdlc/migrate.py check     # 校验磁盘与期望是否一致
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC_AGENTS = os.path.join(ROOT, '.codex', 'agents')
SRC_SDLC = os.path.join(ROOT, '.codex', 'sdlc')
SRC_MEM = os.path.join(ROOT, '.codex', 'agent-memory')
OUT_SDLC = os.path.join(ROOT, '.agents', 'sdlc')
OUT_SKILLS = os.path.join(ROOT, '.agents', 'skills')

# PM 由主会话执行（见 runtime_adapter_trae.md），其余 7 个由 PM 派生
ALL_ROLES = [
    'pm-orchestrator', 'requirement-analyst', 'system-architect',
    'software-developer', 'test-engineer', 'devops-engineer',
    'kb-curator', 'agent-builder',
]

# ── 文本重写规则（顺序敏感：长串在前）────────────────────────────────────────
TEXT_RULES = [
    # 路径（长串在前）
    ('.codex/agent-memory/', '.agents/sdlc/memory/'),
    ('.codex/sdlc/runtime_adapter.md', '.agents/sdlc/runtime_adapter_trae.md'),
    ('.codex/sdlc/', '.agents/sdlc/'),
    ('.codex/agents/', '.agents/skills/'),
    ('.codex/hooks.json', '原 .codex/hooks.json（Trae 无 hooks）'),
    ('.codex/rules/sdlc.rules', '原 .codex/rules/sdlc.rules'),
    ('.codex/config.toml', '原 .codex/config.toml'),
    ('写 `.codex/` 失败', '写 `.agents/sdlc/` 失败'),
    # 平台专属短语
    ('它说明 Codex 工具/记忆/权限差异。', '它说明 Trae 工具/记忆/权限差异。'),
    ('会由启动 hook 注入', '（Trae 无 hooks）不会自动注入，必须显式读取'),
    ('由启动 hook 注入；未收到时必须显式读取',
     '（Trae 无 hooks，不会自动注入）必须显式读取'),
    ('由启动 hook 注入', '（Trae 无 hooks，不会自动注入）必须显式读取'),
    ('（若本轮已收到该文件 hook 注入可免读）',
     '（Trae 无 SubagentStart hook，必须显式读取；文件不存在视为空记忆）'),
    ('若本轮已收到该文件 hook 注入可免读',
     'Trae 无 SubagentStart hook，必须显式读取；文件不存在视为空记忆'),
    ('不要创建不存在的工具或假设 hook 已信任。',
     '不要创建不存在的工具；不要假设 hook 自动化已生效（Trae 无生命周期 hooks）。'),
    ('不要创建不存在的工具或假设 hook 已信任', '不要创建不存在的工具；不要假设 hook 自动化已生效'),
    ('由 pm-orchestrator 调用', '由 sdlc-pm-orchestrator 编排时调用'),
    ('由 pm-orchestrator 编排', '由 sdlc-pm-orchestrator 编排'),
    ('Codex 子代理没有 temperature / top_p / permission_level',
     'Trae 子代理没有 temperature / top_p / permission_level'),
    ('联网只用 受限文档读取脚本，只用于核实 Codex 平台事实',
     '联网只用受限文档读取（WebFetch，仅 Trae 官方文档页），只用于核实 Trae 平台事实；无法核实则 BLOCKED'),
    # Codex CLI 入口 → Trae 技能入口（PM 专用）
    ('`codex "按 .agents/sdlc/pm-orchestrator.md 执行任务"`',
     '`Skill: sdlc-pm-orchestrator`（或直接说「按 SDLC 流程执行」）'),
    ('codex "按 .agents/sdlc/pm-orchestrator.md 执行任务"', 'Skill: sdlc-pm-orchestrator'),
    ('（任一模式）：画像引导（§2）和状态查询照常进行；到需要调用子代理时写检查点，原因写"Agent 工具不可用"，建议用户改用 Skill: sdlc-pm-orchestrator 启动，然后停止。',
     '（任一模式）：画像引导（§2）和状态查询照常进行；到需要调用子代理时写检查点，原因写"Agent 工具不可用"，然后停止。'),
    ('**子代理**（Agent 工具，`agent_type` 取下表名称，`prompt` 为完整 `<agent_invocation>`，一次只调用一个）：',
     '**子代理**（Trae 下统一用 `Agent(subagent_type="general-purpose")`；下表「角色」列决定 prompt 中要求加载的 `Skill: sdlc-<角色>`；`prompt` 为完整 `<agent_invocation>`，一次只调用一个）：'),
    ('SubagentStop hook 自动收集并脱敏、去重写入',
     'Trae 无 SubagentStop hook：PM 在交付阶段显式派生 kb-curator，脱敏、去重写入'),
    ('门控核对 invocation 记录；缺失时把实际事件（agent_type、last_assistant_message、session_id、turn_id）用 JSON 库保存后送入 `python scripts/codex_sdlc/hook_runtime.py stop`，核对输出与收件箱。禁止手拼 JSON 或未脱敏补记。',
     '门控核对 invocation 记录与收件箱。禁止手拼 JSON 或未脱敏补记。'),
    ('SubagentStop hook 会检查', 'PM 会检查（Trae 无 SubagentStop hook）'),
    ('部署请在仓库根运行 Skill: sdlc-pm-orchestrator 后授权',
     '部署须在本会话经用户明确授权后执行（E2 流程）'),
    # shared_protocol 表格与章节的 hook 表述
    ('（SubagentStart hook 注入；缺失时显式读取）', '（Trae 无 hook，必须显式读取）'),
    ('启动 hook 注入前 200 行；缺失时显式读取', '显式读取前 200 行'),
    ('每次子代理结束时 hook 自动抽取的 `<kb_proposals>`', 'PM 派生 kb-curator 抽取的 `<kb_proposals>`'),
    ('SubagentStop hook；PM 补记', 'PM 补记'),
    ('（仅 hook 未记录时补记）', '（PM 补记）'),
    ('hook 检查受覆盖的工具路径，能力边界见 runtime_adapter_trae.md',
     '（Trae 无 hooks）约束靠 prompt 与受限脚本，能力边界见 runtime_adapter_trae.md'),
    ('runtime_adapter.md', 'runtime_adapter_trae.md'),
    # 工具名映射之后才能命中的句式
    ('**子代理**（spawn_agent 工具，`agent_type` 取下表名称',
     '**子代理**（Trae 统一用 `Agent(subagent_type="general-purpose")`；下表「角色」列决定 prompt 中要求加载的 `Skill: sdlc-<角色>`；`agent_type` 原列名保留仅作标识'),
    # 工具名映射
    ('collaboration.spawn_agent', 'Agent'),
    ('spawn_agent(agent_type, message)', 'Agent(subagent_type="general-purpose", prompt=完整 <agent_invocation>)'),
    ('spawn_agent', 'Agent'),
    ('exec_command.workdir', 'Shell 的 cwd 参数'),
    ('exec_command', 'Shell'),
    ('write_stdin', '（Trae Shell 不支持交互写入；长任务用后台运行或足够 timeout）'),
    ('apply_patch', 'Write / Edit'),
    ('rg --files', 'Glob'),
    ('rg -n', 'Grep'),
    ('`rg`', '`Grep`'),
    # Codex CLI 调用示例
    ('Codex CLI 没有 `claude --agent` 等价命令，不发明 `codex --agent`。',
     'Trae 通过 `.agents/skills/` 发现技能；无 `--agent` CLI 参数，角色靠技能加载 + Agent 派生。'),
    ('CLI 从仓库根运行 `codex "按 .codex/sdlc/pm-orchestrator.md 执行……"`',
     'Trae 会话中直接说「按 sdlc-pm 执行……」或调用 Skill: sdlc-pm'),
]

GENERATED_BANNER = (
    '> ⚠️ 本文件由 `scripts/trae_sdlc/migrate.py` 从 `.codex/agents/{src}` 自动生成，'
    '请勿手改；改源文件后重跑脚本。\n'
    '> 运行时为 **Trae**（技能系统 + Agent 子代理）。文中若出现 Codex 专属工具名，'
    '按 `.agents/sdlc/runtime_adapter_trae.md` 的工具映射表理解。\n\n'
)


def rewrite(text: str) -> str:
    for old, new in TEXT_RULES:
        text = text.replace(old, new)
    return text


def read_toml(path: str) -> dict:
    import tomllib
    with open(path, 'rb') as fh:
        return tomllib.load(fh)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ── 期望产物构建（build/check 共用）──────────────────────────────────────────
def build_expected() -> tuple[dict[str, str], dict[str, str]]:
    """返回 (files_to_write, copies_to_make)。files: 目标相对路径 → 内容。"""
    files: dict[str, str] = {}
    copies: dict[str, str] = {}

    # 1) 参考文件：共享协议、项目画像、知识库、模板
    for name in ('shared_protocol.md', 'project_profile.md'):
        src = os.path.join(SRC_SDLC, name)
        with open(src, encoding='utf-8') as fh:
            files[f'.agents/sdlc/{name}'] = rewrite(fh.read())
    for sub in ('knowledge_base', 'templates'):
        for root, _dirs, names in os.walk(os.path.join(SRC_SDLC, sub)):
            for n in names:
                src = os.path.join(root, n)
                rel = os.path.relpath(src, SRC_SDLC).replace(os.sep, '/')
                with open(src, encoding='utf-8') as fh:
                    files[f'.agents/sdlc/{rel}'] = rewrite(fh.read())

    # 2) 记忆：复制（保留原文，不做路径重写以免污染经验内容）
    for role in ALL_ROLES:
        src = os.path.join(SRC_MEM, role, 'MEMORY.md')
        if os.path.exists(src):
            with open(src, encoding='utf-8') as fh:
                copies[f'.agents/sdlc/memory/{role}/MEMORY.md'] = fh.read()

    # 3) 角色技能
    for role in ALL_ROLES:
        t = read_toml(os.path.join(SRC_AGENTS, f'{role}.toml'))
        body = rewrite(t['developer_instructions']).strip()
        desc = rewrite(t['description']).strip().rstrip('。')
        skill = f'sdlc-{role}'
        if role == 'pm-orchestrator':
            trigger = ('当用户明确要求按 SDLC 流程、PM 编排、端到端阶段流程（需求→架构→开发→测试→部署）、'
                       '续跑阶段或知识蒸馏时使用。由主会话承担 PM：读协议后串行派生 general-purpose 子代理，'
                       '子代理用 Skill 加载 sdlc-<role> 角色技能。')
        else:
            trigger = ('SDLC 角色技能：' + desc +
                       '。仅在 sdlc-pm-orchestrator 编排派生时由子代理加载，普通任务不要使用本技能。')
        front = f"---\nname: {skill}\ndescription: {trigger}\n---\n\n"
        files[f'.agents/skills/{skill}/SKILL.md'] = (
            front + GENERATED_BANNER.format(src=f'{role}.toml') + body + '\n'
        )

    return files, copies


def write_manifest(files: dict[str, str], copies: dict[str, str]) -> str:
    src_install = os.path.join(SRC_SDLC, 'INSTALL.md')
    version = 'unknown'
    if os.path.exists(src_install):
        with open(src_install, encoding='utf-8') as fh:
            m = re.search(r'SDLC Agent Suite v(\d+\.\d+)', fh.read())
            if m:
                version = m.group(1)
    manifest = {
        'migrator': 'scripts/trae_sdlc/migrate.py',
        'source_suite_version': version,
        'source': ['.codex/agents', '.codex/sdlc', '.codex/agent-memory'],
        'target': ['.agents/skills', '.agents/sdlc'],
        'roles': ALL_ROLES,
        'generated_files': {k: sha256_text(v) for k, v in sorted(files.items())},
        'copied_memory': {k: sha256_text(v) for k, v in sorted(copies.items())},
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    return text


def do_build() -> int:
    files, copies = build_expected()
    written = 0
    for rel, content in files.items():
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        written += 1
    for rel, content in copies.items():
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(content)
        written += 1
    manifest = write_manifest(files, copies)
    dst = os.path.join(OUT_SDLC, 'migration_manifest_trae.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(manifest)
    print(f'BUILD OK: {written} files + 1 manifest -> .agents/')
    return 0


def do_check() -> int:
    files, copies = build_expected()
    problems = []
    for rel, content in {**files, **copies}.items():
        dst = os.path.join(ROOT, rel)
        if not os.path.exists(dst):
            problems.append(f'MISSING {rel}')
            continue
        with open(dst, encoding='utf-8') as fh:
            if fh.read() != content:
                problems.append(f'DRIFT   {rel}')
    if problems:
        print('CHECK FAILED:')
        for p in problems:
            print(' ', p)
        return 1
    print(f'CHECK OK: {len(files) + len(copies)} files match sources')
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if mode == 'build':
        return do_build()
    if mode == 'check':
        return do_check()
    print('usage: migrate.py [build|check]')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
