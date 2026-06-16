"""inspection_agent.agent —— 自治决策循环（增量③，ARCH §5）。

进程内**只读复用**方案A（PR #19）的生产编排器单专家有界 ReAct 循环来做巡检决策：
直接调用 `Orchestrator._expert({"name":"inspection-expert","query":...})`——该方法本身已
内联 `_handle_read_delegation` / `_run_subexpert`（ARCH §5.3 指定的复用面），并把任何写
提案（直接写工具或 delegate_write）以 `pending_write` 形式返回**而不执行**（绕过 chat 的
`_gate` interrupt）。我们据此拦截写提案，交 WriteAuthPolicy 裁定（OD-01=策略B：全部拦截
转工单），实现"无人值守、零自动写"。

  说明（相对 ARCH §5.3 的实现细化）：架构文本列出的复用面是 `_handle_read_delegation`
  + `_run_subexpert`，本实现复用更上一层的 `Orchestrator._expert`（它在内部调用上述两个
  方法），以**复用生产 ReAct 循环本体**、避免另起一套委托/写拦截逻辑造成漂移（R-06）。
  仍严格满足 ADR-B-004 Option B：只 import、不修改 langgraph_chat、绕过 route/fan_out/gate。

复用边界（OOS-01 / REQ-CON-004）：只 import、绝不修改 api/langgraph_chat/* 任一文件。
Orchestrator 与 execute_write 均为**惰性 import**，使本模块在无 langgraph 的环境下仍可
导入与离线单测（注入 fake orchestrator / write_executor）。
"""

import asyncio
import logging
import os
import time

from . import audit
from .auth import WriteAuthPolicy
from .event_poller import EventPoller
from .work_order import create_from_event

logger = logging.getLogger("freeark.inspection_agent.agent")

INSPECTION_EXPERT = "inspection-expert"
_DEFAULT_POLL_INTERVAL = 30
# 单条事件决策总超时（秒）：覆盖最多 MAX_EXPERT_STEPS 步 LLM 调用；超时→兜底工单。
_DEFAULT_DECISION_TIMEOUT = 300


def get_poll_interval() -> int:
    """轮询间隔秒（INSPECTION_POLL_INTERVAL，默认 30）；非法值回退默认。"""
    try:
        value = int(os.environ.get("INSPECTION_POLL_INTERVAL", ""))
    except (TypeError, ValueError):
        return _DEFAULT_POLL_INTERVAL
    return value if value > 0 else _DEFAULT_POLL_INTERVAL


def get_decision_timeout() -> int:
    """单事件决策总超时秒（INSPECTION_DECISION_TIMEOUT，默认 300）；非法值回退默认。"""
    try:
        value = int(os.environ.get("INSPECTION_DECISION_TIMEOUT", ""))
    except (TypeError, ValueError):
        return _DEFAULT_DECISION_TIMEOUT
    return value if value > 0 else _DEFAULT_DECISION_TIMEOUT


class _EventMeta:
    """事件审计/工单所需的轻量元信息（避免在各处重复 isinstance 分支）。"""
    __slots__ = ("event_id", "event_type", "specific_part", "severity")

    def __init__(self, event_id, event_type, specific_part, severity):
        self.event_id = event_id
        self.event_type = event_type
        self.specific_part = specific_part
        self.severity = severity


class InspectionAgent:
    """自治巡检决策循环。

    依赖均可注入以便离线单测：
      orchestrator    —— 提供 async _expert(state)；缺省惰性构造生产 Orchestrator。
      auth_policy     —— WriteAuthPolicy（缺省读 AUTO_WRITE_POLICY，默认策略B）。
      poller          —— EventPoller。
      write_executor  —— callable(tool, args, operator)->dict；缺省惰性绑定 fa_tools.execute_write。
    """

    def __init__(self, orchestrator=None, auth_policy=None, poller=None, write_executor=None):
        self._orchestrator = orchestrator
        self.auth = auth_policy or WriteAuthPolicy()
        self.poller = poller or EventPoller()
        self._write_executor = write_executor
        self.poll_interval = get_poll_interval()
        self.decision_timeout = get_decision_timeout()
        self._stop = False

    # ── 复用面（惰性 import，离线可注入）─────────────────────────────────
    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from api.langgraph_chat.orchestrator import Orchestrator  # 惰性：需 langgraph
            self._orchestrator = Orchestrator()
        return self._orchestrator

    def _execute_write(self, tool_name, args):
        if self._write_executor is not None:
            return self._write_executor(tool_name, args, "inspection-agent")
        from api.langgraph_chat.fa_tools import execute_write  # 惰性：需 langchain
        return execute_write(tool_name, args, "inspection-agent")

    # ── 主循环 ──────────────────────────────────────────────────────────
    def stop(self):
        """请求优雅退出（供 SIGTERM/SIGINT 处理器调用）。"""
        self._stop = True

    def run_forever(self):
        logger.info("InspectionAgent 启动：poll_interval=%ds decision_timeout=%ds policy=%s",
                    self.poll_interval, self.decision_timeout,
                    os.environ.get("AUTO_WRITE_POLICY", "B"))
        while not self._stop:
            try:
                self.run_once()
            except KeyboardInterrupt:
                logger.info("收到 KeyboardInterrupt，退出巡检循环")
                break
            except Exception:
                logger.exception("巡检轮询未预期异常，sleep 后继续下一轮")
            self._sleep(self.poll_interval)
        logger.info("InspectionAgent 主循环已退出")

    def _sleep(self, seconds):
        """分片 sleep，使 SIGTERM 后最多 ~1s 内退出。"""
        end = time.monotonic() + seconds
        while not self._stop:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))

    def run_once(self) -> int:
        """取一批待巡检事件并逐条串行处理；返回本轮处理事件数。"""
        events = self.poller.poll()
        for event in events:
            try:
                self.process_event(event)
            except Exception:
                logger.exception("处理事件抛未预期异常，重置为 PENDING 待重试：id=%s type=%s",
                                 event.pk, type(event).__name__)
                self._reset_pending(event)
        return len(events)

    # ── 单事件处置（ARCH §5.1 九步）────────────────────────────────────
    def process_event(self, event):
        meta = self._event_meta(event)

        # 步骤1 前置检查：事件已恢复（is_active=False）→ 跳过，不建单。
        if not self._is_active(event):
            self._mark(event, 'SKIPPED')
            audit.log_event_skipped(meta.event_id, meta.event_type, meta.specific_part)
            logger.info("事件已恢复(inactive)，标记 SKIPPED：id=%s part=%s",
                        meta.event_id, meta.specific_part)
            return

        # 步骤2/3 构建巡检指令
        query = self._build_query(event)

        # 步骤4/5 决策（复用生产 _expert 有界 ReAct）；任何异常/超时 → 兜底工单（不丢单）。
        try:
            decision = self._run_decision(query)
        except Exception as exc:  # asyncio.TimeoutError / 网络 / httpx / 委托异常 等
            is_timeout = isinstance(exc, (asyncio.TimeoutError, TimeoutError))
            audit.log_decision_fallback(meta.event_id, meta.event_type, meta.specific_part,
                                        type(exc).__name__, str(exc), timeout=is_timeout)
            logger.error("自治决策失败(%s: %s)，兜底建单：id=%s",
                         type(exc).__name__, exc, meta.event_id)
            self._create_and_done(
                event, meta, diagnosis="",
                recommended_action=f"自治决策未完成（{type(exc).__name__}: {exc}），"
                                   f"已兜底建单待人工巡检。")
            return

        results = decision.get("expert_results", []) if isinstance(decision, dict) else []
        pending = next((r for r in results if "pending_write" in r), None)
        answered = next((r for r in results if "answer" in r), None)

        # 步骤6 写提案 → WriteAuthPolicy 裁定（唯一写入口，无旁路）
        if pending is not None:
            self._handle_write_proposal(event, meta, pending)
        # 步骤7 结论（不可处置/无需写）→ 建单
        elif answered is not None:
            self._create_and_done(
                event, meta,
                diagnosis=self._summarize_delegations(answered),
                recommended_action=(answered.get("answer") or "").strip()
                                   or "（巡检专家未给出明确处置建议，请人工核查）")
        else:
            logger.warning("决策无 pending_write 也无 answer，兜底建单：id=%s", meta.event_id)
            self._create_and_done(
                event, meta, diagnosis="",
                recommended_action="自治决策无有效产出，已兜底建单待人工巡检。")

    def _handle_write_proposal(self, event, meta, pending):
        pw = pending.get("pending_write") or {}
        tool_name = pw.get("tool", "")
        args = pw.get("args", {}) or {}
        result = self.auth.check(tool_name, args, event)

        if result.allowed:
            # 策略 A 白名单放行：唯一可达 execute_write 的路径。建立信任前(策略B)不会到这。
            out = self._execute_write(tool_name, args)
            status = "SUCCESS" if (isinstance(out, dict) and out.get("success")) else "ERROR"
            audit.log_write_executed(meta.event_id, meta.event_type, meta.specific_part,
                                     tool_name, args, status)
            logger.info("写操作已执行(策略A放行)：id=%s tool=%s status=%s",
                        meta.event_id, tool_name, status)
            self._mark(event, 'DONE')
            return

        # 被拦截（策略B 全部拦截 / 策略A 越界）→ 建单，记录被拦截的写提案。
        # 结构化 tool+args 一并落库（write_status=PENDING），供工单页管理员审批后执行。
        audit.log_write_blocked(meta.event_id, meta.event_type, meta.specific_part,
                                tool_name, args, result.reason)
        self._create_and_done(
            event, meta,
            diagnosis=self._summarize_delegations(pending),
            recommended_action=self._describe_blocked_write(tool_name, args, result.reason),
            proposed_tool=tool_name, proposed_args=args)

    # ── 工单 + 状态持久化（DB 失败 → 重置 PENDING 下轮重试，ARCH §5.2）──
    def _create_and_done(self, event, meta, diagnosis, recommended_action,
                         proposed_tool='', proposed_args=None):
        try:
            work_order, created = create_from_event(
                event, diagnosis=diagnosis, recommended_action=recommended_action,
                proposed_tool=proposed_tool, proposed_args=proposed_args)
            if created:
                audit.log_workorder_created(meta.event_id, meta.event_type, meta.specific_part,
                                            work_order.ticket_id, meta.severity)
                logger.info("已建工单 %s：id=%s part=%s",
                            work_order.ticket_id, meta.event_id, meta.specific_part)
            else:
                audit.log_workorder_existed(meta.event_id, meta.event_type, meta.specific_part,
                                            work_order.ticket_id)
                logger.info("活跃工单已存在(%s)，未重复建单：id=%s",
                            work_order.ticket_id, meta.event_id)
            self._mark(event, 'DONE')
        except Exception:
            logger.exception("工单/状态持久化失败，重置 PENDING 待下轮重试：id=%s", meta.event_id)
            self._reset_pending(event)

    # ── 辅助 ────────────────────────────────────────────────────────────
    def _run_decision(self, query):
        coro = self.orchestrator._expert(
            {"name": INSPECTION_EXPERT, "query": query, "messages": []})
        return asyncio.run(asyncio.wait_for(coro, timeout=self.decision_timeout))

    @staticmethod
    def _event_meta(event) -> _EventMeta:
        from api.models import FaultEvent
        if isinstance(event, FaultEvent):
            return _EventMeta(event.pk, 'fault_event', event.specific_part, event.severity)
        # CondensationWarningEvent：无 severity 字段，用 warning_type 作级别
        return _EventMeta(event.pk, 'condensation_warning_event',
                          event.specific_part, getattr(event, 'warning_type', ''))

    @staticmethod
    def _is_active(event) -> bool:
        event.refresh_from_db(fields=['is_active'])
        return bool(event.is_active)

    @staticmethod
    def _mark(event, status):
        event.inspection_status = status
        event.save(update_fields=['inspection_status', 'updated_at'])

    @staticmethod
    def _reset_pending(event):
        event.inspection_status = 'PENDING'
        event.inspection_started_at = None
        event.save(update_fields=['inspection_status', 'inspection_started_at', 'updated_at'])

    @staticmethod
    def _summarize_delegations(result) -> str:
        dl = result.get("delegations") or []
        if not dl:
            return ""
        return "；".join(
            f"{d.get('target_agent', '?')}/{d.get('intent', '?')}={d.get('status', '?')}"
            for d in dl)

    @staticmethod
    def _describe_blocked_write(tool_name, args, reason) -> str:
        args = args or {}
        if tool_name == "set_device_params":
            sp = args.get("specific_part", "?")
            items = args.get("items") or []
            parts = "、".join(
                f"{i.get('param_name', '?')}→{i.get('new_value', '?')}"
                for i in items) or "(无参数项)"
            detail = f"设备 {sp} 参数 {parts}"
        elif tool_name == "trigger_refresh":
            detail = f"触发设备 {args.get('specific_part', '?')} 按需采集刷新"
        else:
            detail = f"{tool_name}({args})"
        return (f"巡检专家提案写处置：{detail}。"
                f"已按授权策略拦截（{reason}），未执行，转人工确认处置。")

    @staticmethod
    def _build_query(event) -> str:
        from api.models import FaultEvent
        if isinstance(event, FaultEvent):
            ctx = (f"- 房号/专有部分：{event.specific_part}\n"
                   f"- 设备序列号：{event.device_sn}\n"
                   f"- 故障码：{event.fault_code}；故障大类：{event.fault_type}\n"
                   f"- 故障描述：{event.fault_message}\n"
                   f"- 严重级别：{event.severity}")
            kind = "故障事件"
        else:
            ctx = (f"- 房号/专有部分：{event.specific_part}\n"
                   f"- 设备序列号：{event.device_sn}\n"
                   f"- 预警类型：{getattr(event, 'warning_type', '')}\n"
                   f"- 预警内容：{getattr(event, 'warning_message', '')}\n"
                   f"- 触发 condensation_alarm 原始值：{getattr(event, 'condensation_alarm_value', '')}\n"
                   f"- 露点/NTC/湿度快照：{getattr(event, 'dew_point_temp', '')} / "
                   f"{getattr(event, 'ntc_temp', '')} / {getattr(event, 'humidity', '')}")
            kind = "结露预警事件"
        return (
            f"【自治巡检任务·无人值守】检测到一条{kind}，请自主分析并给出处置决策：\n"
            f"{ctx}\n\n"
            f"请：①必要时调用 delegate_knowledge 分析成因、delegate_read 取该户相关设备数据；"
            f"②若判断需要下发/修改设备参数处置，调用 delegate_write 提交处置提案"
            f"（当前为无人值守自治场景，系统将据写授权策略裁定是否执行，你无权也不要声称已执行）；"
            f"③若无需写处置或不可自动处置，请用简洁中文说明巡检结论、成因与建议的人工处置措施。")
