"""
api.langgraph_chat —— LangGraph 多 agent 编排（替换 OpenClaw 的生产包）

阶段 A（影子接入）：本包随 CHAT_BACKEND=langgraph 开关被选中，默认不启用，
生产仍走 OpenClaw。包名特意取 langgraph_chat 而非 langgraph，避免遮蔽 pip
安装的第三方 langgraph 顶层包（import footgun）。

设计与迁移计划见 agents/langgraph-poc/{README.md, PHASE3_ROLLOUT.md}。

本 __init__ 刻意保持轻量：不在 import 包时构造编排图/LLM/工具，
避免 migrate / collectstatic 等管理命令误触发建连。编排器由 adapter 惰性构造，
或在 api.apps.ApiConfig.ready() 里按开关预热。
"""
