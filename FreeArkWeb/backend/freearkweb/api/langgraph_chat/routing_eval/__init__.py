"""
api.langgraph_chat.routing_eval —— 意图路由评测集 + 评测 harness（P1-3）

目的：把散落在 scripts/analysis/router_probe.py、单测 RouterClassifierTests、以及生产
事故注释里的路由用例，收敛成**一份外置、可版本化、可增长的 labeled 数据集**
（dataset.jsonl），并配套一个产出指标（不止 pass 数）的评测 harness。

两条用途，一套数据集：
  - 离线模式（默认，确定性、可进 CI、免费）：classify_experts(llm=None, q) = 纯关键词路由
    + DEFAULT 兜底。度量「关键词路由地板」——这正是 P0-1（关键词短路）需要的数。
  - live 模式（--live，需 DeepSeek key，建议在 Pi 上跑）：用生产同款 router_llm(temp 0)
    度量真实 LLM 路由质量。

本包刻意保持 langchain-free（仅 stdlib + 读 router.py 的纯函数/常量），便于单测与离线
评测在不装 langchain 的环境跑。live 路径由 CLI（scripts/analysis/routing_eval.py）惰性
注入 classifier，本包不构造任何 LLM。

详见 README.md。
"""
