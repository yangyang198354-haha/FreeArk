"""inspection_agent.auth —— 自治写授权层（OD-01 落地，ARCH §6）。

无人值守自治场景下，inspection-expert 的 delegate_write 提案是否自动执行，**只由本模块
裁定**。架构层面的唯一写入口约束：execute_write() 仅可在 WriteAuthPolicy.check() 返回
AuthResult(allowed=True) 之后被调用，无任何旁路（ARCH §6.3）。

策略（AUTO_WRITE_POLICY 环境变量，默认 "B"）：
  - 策略 B（PolicyB，**本期拍板默认**）：始终拦截，零自动写、全部转工单。
  - 策略 A（PolicyA，备选，未启用）：INSPECTION_WRITE_WHITELIST 白名单内参数自动执行，
    越界转工单。**策略 A 为代码接缝，未经生产验证**：启用前须按 OQ-05 与运维共同定义
    安全区间，并复核与真实写工具 schema（set_device_params 的 items[] 结构）的映射。
    从 B 升级到 A 只需改 .env，无需改代码（EV-01，建议 30 天 LLM 提案吻合率≥90% 后再升）。
"""

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("freeark.inspection_agent.auth")

# AuthResult.reason 取值常量（与审计日志 policy_reason 对齐，ARCH §6.1/§9.1）
REASON_POLICY_B = "POLICY_B_NO_AUTO_WRITE"
REASON_OUT_OF_WHITELIST = "OUT_OF_WHITELIST"
REASON_APPROVED_WHITELIST = "APPROVED_BY_WHITELIST"

# set_device_params 中无需校验的非业务参数（specific_part 为定位、operator_override 为注入）
_NON_VALUE_PARAMS = frozenset({"specific_part", "operator_override"})


@dataclass(frozen=True)
class AuthResult:
    """写授权裁定结果。allowed=True 是调用 execute_write() 的唯一前提。"""
    allowed: bool
    reason: str


def _get_policy_name() -> str:
    """读取当前生效策略（每次 check 读取，便于 .env 切换与测试覆写）。默认 B。"""
    return os.environ.get("AUTO_WRITE_POLICY", "B").strip().upper() or "B"


def _load_whitelist() -> dict:
    """从 INSPECTION_WRITE_WHITELIST（JSON）解析白名单；缺省/非法 → 空 dict（即全拒）。"""
    raw = os.environ.get("INSPECTION_WRITE_WHITELIST", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.error("INSPECTION_WRITE_WHITELIST 解析失败，按空白名单（全拒）处理: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        logger.error("INSPECTION_WRITE_WHITELIST 须为 JSON 对象，实际为 %s，按空白名单处理",
                     type(parsed).__name__)
        return {}
    return parsed


class PolicyB:
    """策略 B（本期默认）：始终拦截，无任何例外路径（ARCH §6.1）。"""

    def check(self, tool_name: str, args: dict, event=None) -> AuthResult:  # noqa: ARG002
        return AuthResult(allowed=False, reason=REASON_POLICY_B)


class PolicyA:
    """策略 A（备选，未启用）：白名单内参数自动执行，越界转工单（ARCH §6.1）。

    安全默认值：任何无法**肯定**通过校验的情况一律拒绝（default-deny）——
    工具不在白名单、参数无对应规则、取值无法解析为数值、越界，均返回 allowed=False。

    已知限制（启用前须闭环，OQ-05）：max_delta（单次变化量）需要参数当前基线值，
    本授权层不持有读数，故当前仅强制 abs_min/abs_max 绝对区间，max_delta 暂不强制。
    """

    def __init__(self, whitelist: dict):
        self.whitelist = whitelist or {}

    def check(self, tool_name: str, args: dict, event=None) -> AuthResult:  # noqa: ARG002
        rules = self.whitelist.get(tool_name)
        if rules is None:
            return AuthResult(allowed=False, reason=REASON_OUT_OF_WHITELIST)
        pairs = self._extract_param_values(tool_name, args or {})
        # 无可校验参数（如 trigger_refresh）：仅当该工具被显式以空规则白名单化时放行
        if not pairs:
            if rules == {}:
                return AuthResult(allowed=True, reason=REASON_APPROVED_WHITELIST)
            return AuthResult(allowed=False, reason=REASON_OUT_OF_WHITELIST)
        for param_name, raw_value in pairs:
            rule = rules.get(param_name)
            if rule is None:
                return AuthResult(allowed=False, reason=REASON_OUT_OF_WHITELIST)
            if not self._value_within_bounds(raw_value, rule):
                return AuthResult(allowed=False, reason=REASON_OUT_OF_WHITELIST)
        return AuthResult(allowed=True, reason=REASON_APPROVED_WHITELIST)

    @staticmethod
    def _extract_param_values(tool_name: str, args: dict):
        """抽取待校验的 (param_name, raw_value) 列表，兼容两种写工具入参形态。"""
        if tool_name == "set_device_params":
            items = args.get("items") or []
            return [(it.get("param_name"), it.get("new_value"))
                    for it in items if isinstance(it, dict)]
        # 通用扁平形态（ARCH §6.1 伪码），剔除非业务参数
        return [(k, v) for k, v in args.items() if k not in _NON_VALUE_PARAMS]

    @staticmethod
    def _value_within_bounds(raw_value, rule: dict) -> bool:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return False  # 无法解析 → default-deny
        abs_min = rule.get("abs_min")
        abs_max = rule.get("abs_max")
        if abs_min is not None and value < float(abs_min):
            return False
        if abs_max is not None and value > float(abs_max):
            return False
        return True


class WriteAuthPolicy:
    """写授权策略调度器：唯一写授权入口（ARCH §6.1）。

    每次 check() 按 AUTO_WRITE_POLICY 实时分派到 PolicyB（默认）或 PolicyA；
    白名单在实例化时解析一次（PolicyA 用），策略切换走环境变量。
    """

    def __init__(self):
        self.whitelist = _load_whitelist()

    def check(self, tool_name: str, args: dict, event=None) -> AuthResult:
        policy = _get_policy_name()
        if policy == "A":
            return PolicyA(self.whitelist).check(tool_name, args, event)
        # 默认与一切非 "A" 取值 → 策略 B（零自动写）
        return PolicyB().check(tool_name, args, event)
