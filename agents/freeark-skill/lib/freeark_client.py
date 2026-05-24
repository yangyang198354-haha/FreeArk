"""
FreeArk Skill — HTTP 客户端封装

文档引用：MOD-SK-01 (HTTP 客户端规范), ARCH-LOBSTER-002 ADR-001, ADR-005a
版本：2.0.0
"""

import os
import requests

FREEARK_BASE = os.environ.get("FREEARK_API_BASE", "http://127.0.0.1:8000")
FREEARK_TOKEN = os.environ.get("FREEARK_AGENT_TOKEN", "")


class FreeArkClient:
    """
    统一 HTTP 客户端。

    安全约束（来自 ARCH-LOBSTER-002 §5.3）：
    - Token 从环境变量 FREEARK_AGENT_TOKEN 读取，不硬编码
    - HTTP 目标强制为 127.0.0.1:8000（防 SSRF hardcheck）
    - 日志中仅输出 Token 前 8 字符
    - Tier-1 超时 5 秒，Tier-2 超时 8 秒
    """

    def __init__(self):
        token = FREEARK_TOKEN
        if not token:
            raise RuntimeError(
                "FREEARK_AGENT_TOKEN 环境变量未设置。"
                "请在 openclaw.json 的 secrets/env 段配置 Token 注入。"
            )
        base = FREEARK_BASE
        if "127.0.0.1:8000" not in base:
            raise RuntimeError(
                f"非法 API 地址（SSRF 防护）：{base}。"
                "FREEARK_API_BASE 只允许 http://127.0.0.1:8000"
            )
        self._token = token
        self._base = base
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def get(self, path: str, params: dict = None, timeout: int = 5) -> dict:
        """
        Tier-1 只读 GET 请求。

        Returns:
            {"success": True, "data": ..., "http_status": 200}
            {"success": False, "error": "...", "http_status": N}
        """
        url = f"{self._base}{path}"
        try:
            resp = self._session.get(url, params=params or {}, timeout=timeout)
            if resp.status_code == 200:
                return {"success": True, "data": resp.json(), "http_status": 200}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "http_status": resp.status_code,
                }
        except requests.exceptions.Timeout:
            return {"success": False, "error": f"请求超时（>{timeout}s）", "http_status": 0}
        except requests.exceptions.ConnectionError as e:
            return {"success": False, "error": f"连接失败: {e}", "http_status": 0}
        except Exception as e:
            return {"success": False, "error": f"未知错误: {e}", "http_status": 0}

    def post(self, path: str, data: dict, timeout: int = 8) -> dict:
        """
        Tier-2 写操作 POST 请求（超时 8 秒，含 MQTT ACK 等待）。
        """
        url = f"{self._base}{path}"
        try:
            resp = self._session.post(url, json=data, timeout=timeout)
            if resp.status_code in (200, 201):
                return {"success": True, "data": resp.json(), "http_status": resp.status_code}
            else:
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "http_status": resp.status_code,
                }
        except requests.exceptions.Timeout:
            return {"success": False, "error": f"请求超时（>{timeout}s）", "http_status": 0}
        except requests.exceptions.ConnectionError as e:
            return {"success": False, "error": f"连接失败: {e}", "http_status": 0}
        except Exception as e:
            return {"success": False, "error": f"未知错误: {e}", "http_status": 0}

    def log_token_hint(self) -> str:
        """安全日志：仅返回 Token 前 8 字符（REQ-NFR-007）。"""
        return (self._token[:8] + "...") if self._token else "NOT_SET"
