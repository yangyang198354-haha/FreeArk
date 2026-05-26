<?xml version="1.0" encoding="UTF-8"?>
<phase_status
  project="freeark_lobster_reasoning_stream"
  flow_mode="PARTIAL_FLOW"
  scope="GROUP_A → GROUP_B (暂停)"
  created_at="2026-05-25T00:00:00+08:00"
  last_updated="2026-05-26T00:00:00+08:00"
  pm_agent="main_agent_pm (claude-sonnet-4-6)"
>

  <!-- ===== GROUP_A：需求分析 ===== -->
  <group id="GROUP_A" agent="sub_agent_requirement_analyst">
    <phase id="PHASE_01" name="需求分析">
      <status>APPROVED</status>
      <output_files>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/requirements_spec.md</file>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/user_stories.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-25T12:00:00+08:00</completed_at>
    </phase>
    <gate_review id="GATE-A-001" status="PASS">
      <gate_decision>PASS</gate_decision>
      <reviewed_at>2026-05-25T12:00:00+08:00</reviewed_at>
      <findings>
        <finding severity="NONE">所有需求（REQ-FUNC-008~012, REQ-NFR-005~009）有明确来源引用</finding>
        <finding severity="NONE">所有 AC 使用 Given/When/Then 格式</finding>
        <finding severity="NONE">无发明需求；无架构内容混入</finding>
        <finding severity="NONE">用户故事覆盖全部需求，依赖关系明确</finding>
      </findings>
    </gate_review>
  </group>

  <!-- ===== GROUP_B：系统架构 + 模块/接口设计 ===== -->
  <group id="GROUP_B" agent="sub_agent_system_architect">
    <phase id="PHASE_03" name="系统架构设计">
      <status>APPROVED</status>
      <output_files>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/architecture_design.md</file>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/tech_stack.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T00:00:00+08:00</completed_at>
    </phase>
    <phase id="PHASE_04" name="模块/接口设计">
      <status>APPROVED</status>
      <output_files>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/module_design.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T00:00:00+08:00</completed_at>
    </phase>
    <gate_review id="GATE-B-001" status="PASS">
      <gate_decision>PASS</gate_decision>
      <reviewed_at>2026-05-26T00:00:00+08:00</reviewed_at>
      <findings>
        <finding severity="NONE">所有 REQ-FUNC-008~012 均有对应模块覆盖（MOD-BE-02 v1.3, MOD-BE-01 v1.2, MOD-FE-01 v1.1）</finding>
        <finding severity="NONE">无循环依赖（MOD-BE-02←MOD-BE-01←MOD-FE-01 单向依赖链）</finding>
        <finding severity="NONE">ADR-006/ADR-008 各有 ≥3 方案；ADR-007 提供向后兼容矩阵（4 场景分析）</finding>
        <finding severity="NONE">接口已类型化：stream_chat() → AsyncGenerator[tuple[str,str], None]；WS 消息格式明确定义</finding>
        <finding severity="NONE">架构约束 ARCH-C-001~005 明确列出，所有不确定项（字段名、camelCase）已标注为开放风险</finding>
      </findings>
    </gate_review>
  </group>

  <!-- ===== GROUP_C：软件实现 ===== -->
  <group id="GROUP_C" agent="sub_agent_software_developer">
    <phase id="PHASE_05" name="实现计划">
      <status>AWAITING_REVIEW</status>
      <output_files>
        <file status="WRITTEN">docs/specs/freeark_lobster_reasoning_stream/implementation_plan.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T09:00:00+08:00</completed_at>
    </phase>
    <phase id="PHASE_06" name="代码实现 + Code Review">
      <status>AWAITING_REVIEW</status>
      <output_files>
        <file status="WRITTEN">FreeArkWeb/backend/freearkweb/api/openclaw_adapter.py (v1.3)</file>
        <file status="WRITTEN">FreeArkWeb/backend/freearkweb/api/consumers.py (v1.2)</file>
        <file status="WRITTEN">FreeArkWeb/frontend/src/views/ChatView.vue (v1.1)</file>
        <file status="WRITTEN">FreeArkWeb/backend/freearkweb/freearkweb/settings.py (OPENCLAW_REASONING_EFFORT 追加)</file>
        <file status="WRITTEN">FreeArkWeb/backend/freearkweb/api/tests.py (ChatConsumerReasoningProtocolTest + ChatConsumerNoReasoningCompatTest 追加)</file>
        <file status="WRITTEN">docs/specs/freeark_lobster_reasoning_stream/code_review_report.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T09:00:00+08:00</completed_at>
    </phase>
  </group>

  <!-- PM 决策记录：US-RSN-001 走法 B 选定 -->
  <pm_decision id="PM-DEC-001" time="2026-05-26T08:00:00+08:00">
    <topic>US-RSN-001 字段名探查走法选择</topic>
    <decision>走法 B：developer 按 ADR-006 防御性解析（_REASONING_FIELD='reasoningDelta' + kind==reasoning 双路）实现 v1.3，
    上线后通过日志 reasoning_tokens 值验证是否命中；若未命中，由 devops 在 GROUP_E deployment_plan 中执行临时 logger 探查并二次迭代。
    理由：走法 A 需在 GROUP_C 中途暂停动生产，违反 SDLC 分组边界；走法 B 与 ADR-006 设计意图完全一致。</decision>
    <risk>若 OpenClaw 使用未预期的字段结构（如独立事件流），则 reasoning_tokens 始终=0，需 GROUP_E 探查后重开 PATCH 迭代。</risk>
  </pm_decision>

  <gate_review id="GATE-C-001" status="PASS_WITH_CONDITIONS">
    <gate_decision>PASS_WITH_CONDITIONS</gate_decision>
    <reviewed_at>2026-05-26T09:00:00+08:00</reviewed_at>
    <findings>
      <finding severity="NONE">所有模块已实现：adapter v1.3、consumer v1.2、ChatView.vue v1.1</finding>
      <finding severity="NONE">code_review 无 CRITICAL finding，无 MAJOR finding（0+0）</finding>
      <finding severity="NONE">yield 协议同步验证通过（adapter tuple / consumer 解包一致）</finding>
      <finding severity="NONE">日志不含 token 文本（REQ-NFR-007 满足）</finding>
      <finding severity="NONE">TransactionTestCase 兼容性测试编写完整（US-RSN-010）</finding>
      <finding severity="NONE">settings.py 只读 env var，未动 .env（强制纪律满足）</finding>
      <finding severity="MINOR">CR-M-001: stream_incomplete 日志可加 reasoning_ms/content_ms（P2 迭代）</finding>
      <finding severity="MINOR">CR-M-002: details 折叠三角无过渡动画（UI 优化迭代）</finding>
      <finding severity="MINOR">CR-M-003: async_gen mock 不可重用，GROUP_D 完善时注意</finding>
    </findings>
    <open_conditions>
      <condition id="OC-C-001">走法B风险：若生产 reasoning_tokens=0，触发 GROUP_E 探查流程（implementation_plan.md §3.2）</condition>
    </open_conditions>
  </gate_review>

  <!-- ===== GROUP_D：测试阶段 ===== -->
  <group id="GROUP_D" agent="sub_agent_test_engineer">
    <phase id="PHASE_07" name="测试计划">
      <status>APPROVED</status>
      <output_files>
        <file status="APPROVED">docs/specs/freeark_lobster_reasoning_stream/test_plan.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T11:00:00+08:00</completed_at>
    </phase>
    <phase id="PHASE_08" name="测试执行">
      <status>APPROVED</status>
      <output_files>
        <file status="APPROVED">FreeArkWeb/backend/freearkweb/api/tests/test_reasoning_stream.py（GROUP_C 迁入 + GROUP_D 7 个新测试类：AdapterDeltaParseLogicTest, AdapterBuildChatSendFrameTest, AdapterReasoningEffortWarningTest, AdapterGetConfigReasoningEffortTest, AdapterToWsUrlTest, AdapterStatLogTest, ChatConsumerEdgeCasesTest）</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T12:00:00+08:00</completed_at>
      <test_results>
        <total>34</total>
        <passed>34</passed>
        <failed>0</failed>
        <skipped>0</skipped>
        <pass_rate>100%</pass_rate>
      </test_results>
    </phase>
    <phase id="PHASE_09" name="覆盖率与报告">
      <status>APPROVED</status>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T12:00:00+08:00</completed_at>
    </phase>
  </group>

  <!-- PM 决策记录：GROUP_C/D 测试文件位置 Bug 修复 -->
  <pm_decision id="PM-DEC-002" time="2026-05-26T11:30:00+08:00">
    <topic>GROUP_C ae089f1 commit 的测试结构性 Bug 修复</topic>
    <decision>用户决议方案 1：新建 api/tests/test_reasoning_stream.py，回滚 api/tests.py 到 00433c7 状态。
    Bug 根因：api/ 下同时存在 tests.py 文件和 tests/ 包（含 __init__.py），Python 解析 api.tests
    优先取包；ae089f1 把测试追加到 tests.py 导致 `python manage.py test api.tests.&lt;Class&gt;` 无法发现。
    修复后 34/34 测试全部通过。</decision>
    <risk>无残留风险；legacy tests.py 中 35+ 老测试类的发现性问题独立处理，不在本期 scope。</risk>
  </pm_decision>

  <gate_review id="GATE-D-001" status="PASS">
    <gate_decision>PASS</gate_decision>
    <reviewed_at>2026-05-26T12:00:00+08:00</reviewed_at>
    <findings>
      <finding severity="NONE">单次 100% 通过：Ran 34 tests in 1.183s — OK（unit 30 + integration 4）</finding>
      <finding severity="NONE">测试位置已修复，python manage.py test api.tests.test_reasoning_stream 可发现并执行所有 34 个用例</finding>
      <finding severity="NONE">覆盖 US-RSN-002/003/004/008/010 全部 AC（AC-009-*, AC-010-*, AC-012-*, AC-NFR-005-01, AC-NFR-007-01）</finding>
      <finding severity="NONE">channels.testing 依赖 daphne 4.2.1 已装（开发/测试环境），生产用 uvicorn 不受影响</finding>
      <finding severity="NONE">CR-M-003（async_gen mock 不可重用）已在 GROUP_D 用例中通过单次使用规避</finding>
    </findings>
  </gate_review>

  <!-- ===== GROUP_E：DevOps 部署计划 ===== -->
  <group id="GROUP_E" agent="sub_agent_devops_engineer">
    <phase id="PHASE_10" name="部署计划文档">
      <status>AWAITING_REVIEW</status>
      <output_files>
        <file status="WRITTEN">docs/specs/freeark_lobster_reasoning_stream/deployment_plan.md</file>
        <file status="WRITTEN">docs/specs/freeark_lobster_reasoning_stream/cicd_pipeline.md</file>
      </output_files>
      <retry_count>0</retry_count>
      <completed_at>2026-05-26T14:00:00+08:00</completed_at>
    </phase>
  </group>

  <gate_review id="GATE-E-001" status="PASS">
    <gate_decision>PASS</gate_decision>
    <reviewed_at>2026-05-26T14:00:00+08:00</reviewed_at>
    <findings>
      <finding severity="NONE">deployment_plan.md 已覆盖所有必须章节：前置检查、ARCH-C-002 同批次约束、前端构建、git pull 部署、systemd 重启清单、US-RSN-001 走法B后置验证（§6）、US-RSN-009 基线测量（§7）、回滚方案（§9）、部署后验证（§8）</finding>
      <finding severity="NONE">ARCH-C-002 同批次部署约束已在文档中用显著标注（§2，"最高优先级约束"）列出合法/非法组合矩阵</finding>
      <finding severity="NONE">US-RSN-001 字段探查流程（§6.3）完整：reasoning_tokens=0 触发条件、PROBE logger 步骤、_REASONING_FIELD 单行改动、探查后清理、arch doc 更新</finding>
      <finding severity="NONE">US-RSN-009 基线测量步骤（§7）完整：reasoning_ms 采集方法（APP_LOG_LEVEL=INFO + journalctl）、T0/T0' 双轮测量、50% 效果比门控、RISK-003/004 上报路径</finding>
      <finding severity="NONE">回滚方案（§9）完整：git checkout 旧 commit 特定文件、dist 备份恢复、systemd 重启、回滚验证；回滚决策须 PM/运维确认</finding>
      <finding severity="NONE">PRODUCTION_DEPLOY_CONFIRM 强制等待点在 cicd_pipeline.md Gate 1 中明确标注，不得绕过</finding>
      <finding severity="NONE">cicd_pipeline.md 以 ASCII 流程图 + 手动步骤覆盖完整 pipeline：Stage 1 本地验证 → Gate 1 CONFIRM → Stage 2 前置检查 → Stage 3 代码部署 → Stage 4 前端构建 → Stage 5 服务重启 → Stage 6 验证 → Stage 7A 上线后验证</finding>
      <finding severity="NONE">禁止 Docker、禁止 pscp 在 deployment_plan.md §0 和 §4 明确标注</finding>
      <finding severity="NONE">不含任何 SSH 密钥、token 明文；OPENCLAW_GATEWAY_TOKEN 仅以 cut -c1-8 比对前缀方式验证，不打印完整值</finding>
    </findings>
  </gate_review>

  <orchestration_status>GROUP_E_DOCS_APPROVED_AWAITING_PRODUCTION_DEPLOY_CONFIRM</orchestration_status>

  <audit_log>
    <log time="2026-05-25T12:00:00+08:00" state="PM_GATE_PASS" action="GROUP_A 门控通过" result="PASS" invocation_id="GROUP_A-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-25T12:00:00+08:00" state="PM_INVOKE_AGENT" action="启动 sub_agent_system_architect GROUP_B" result="IN_PROGRESS" invocation_id="GROUP_B-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T00:00:00+08:00" state="PM_GATE_PASS" action="GROUP_B 门控通过" result="PASS" invocation_id="GROUP_B-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T08:00:00+08:00" state="PM_INVOKE_AGENT" action="启动 sub_agent_software_developer GROUP_C，走法B（防御性解析）" result="IN_PROGRESS" invocation_id="GROUP_C-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T09:00:00+08:00" state="PM_GATE_PASS" action="GROUP_C 门控通过（PASS_WITH_CONDITIONS，3 MINOR）" result="PASS_WITH_CONDITIONS" invocation_id="GROUP_C-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T09:00:00+08:00" state="PM_USER_CONFIRMED" action="用户 CONFIRM 进入 GROUP_D 测试阶段" result="CONFIRMED" invocation_id="CONFIRM-002" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T10:00:00+08:00" state="PM_INVOKE_AGENT" action="启动 sub_agent_test_engineer GROUP_D：test_plan.md 编写 + 单元/集成测试追加" result="IN_PROGRESS" invocation_id="GROUP_D-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T11:30:00+08:00" state="PM_BUG_DETECTED" action="发现 GROUP_C ae089f1 测试位置 Bug：tests.py vs tests/ 包冲突，导致测试不可发现" result="BLOCKING" invocation_id="GROUP_D-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T11:45:00+08:00" state="PM_USER_DECISION" action="用户决议方案 1：迁移到 api/tests/test_reasoning_stream.py + 回滚 tests.py" result="CONFIRMED" invocation_id="PM-DEC-002" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T12:00:00+08:00" state="PM_GATE_PASS" action="GROUP_D 门控通过：34/34 测试 100% 通过" result="PASS" invocation_id="GROUP_D-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T14:00:00+08:00" state="PM_INVOKE_AGENT" action="启动 sub_agent_devops_engineer GROUP_E：deployment_plan.md + cicd_pipeline.md（仅文档，不执行实际部署）" result="IN_PROGRESS" invocation_id="GROUP_E-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T14:00:00+08:00" state="PM_GATE_PASS" action="GROUP_E 门控通过（GATE-E-001 PASS）：deployment_plan + cicd_pipeline 覆盖所有必须章节" result="PASS" invocation_id="GROUP_E-001" trace_id="freeark_lobster_reasoning_stream"/>
    <log time="2026-05-26T14:00:00+08:00" state="PM_AWAIT_DEPLOY_CONFIRM" action="等待用户明确 PRODUCTION_DEPLOY_CONFIRM 信号，文档阶段完成" result="WAITING" invocation_id="CONFIRM-E-001" trace_id="freeark_lobster_reasoning_stream"/>
  </audit_log>

</phase_status>
