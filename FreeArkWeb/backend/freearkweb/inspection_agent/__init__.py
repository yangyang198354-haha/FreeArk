"""inspection_agent —— 自治巡检 Agent（v1.1.0-AIA，方案 B）。

方案 A（chat 链路委托，已上线 PR #19）的独立扩展子系统：以独立 systemd 服务
`freeark-inspection-agent`（Django Management Command）运行，DB 轮询 fault_event /
condensation_warning_event 的待巡检事件，进程内**只读复用** api.langgraph_chat.* 的
单专家有界 ReAct 委托能力，按 WriteAuthPolicy（OD-01=策略B：零自动写、全部转工单）
落 WorkOrder 工单。

设计原则（ARCH §1.1）：
  1. 不修改现有 chat 链路：api/langgraph_chat/ 下文件仅 import、绝不 edit/write。
  2. 最小新依赖：复用现有 Django ORM + MySQL + systemd，不引 Redis/MQ/Docker。
  3. 写操作强隔离：execute_write() 只能在 WriteAuthPolicy.check() 返回 allowed=True
     后调用，无任何旁路。

模块（按增量交付）：
  增量② —— auth / event_poller / work_order / audit（本目录，纯逻辑，可离线单测）
  增量③ —— agent（决策循环，import 复用方案A） + management/commands/run_inspection_agent

注意：本 __init__ 刻意不在包导入时 import 任何子模块，避免在 Django app registry
就绪前触发模型导入（AppRegistryNotReady）。请按需 `from inspection_agent.auth import ...`。
"""

__all__: list = []
