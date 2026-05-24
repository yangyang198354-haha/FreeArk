"""
FreeArk Skill — HTTP 客户端（stdlib urllib，零外部依赖）

依赖说明：使用 Python 3 标准库 urllib.request，无需 venv 安装 requests
（FreeArk venv 与系统 Python 共享解释器，但 site-packages 未装 requests）。

文档引用：MOD-SK-01, ARCH-LOBSTER-002 ADR-001/ADR-005a
版本：2.0.1（urllib 改写）
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

FREEARK_BASE = os.environ.get("FREEARK_API_BASE", "http://127.0.0.1:8000")
FREEARK_TOKEN = os.environ.get("FREEARK_AGENT_TOKEN", "")


class FreeArkClient:
    """统一 HTTP 客户端，stdlib only。

    安全约束（ARCH-LOBSTER-002 §5.3）：
    - Token 从 FREEARK_AGENT_TOKEN env 读取，不硬编码
    - HTTP 目标强制 127.0.0.1:8000（SSRF hardcheck）
    - Tier-1 超时 5s，Tier-2 超时 8s
    """

    def __init__(self):
        if not FREEARK_TOKEN:
            raise RuntimeError(
                "FREEARK_AGENT_TOKEN 环境变量未设置。"
                "请检查 openclaw-gateway.service 的 EnvironmentFile 配置。"
            )
        if "127.0.0.1:8000" not in FREEARK_BASE:
            raise RuntimeError(
                f"非法 API 地址（SSRF 防护）：{FREEARK_BASE}。"
                "FREEARK_API_BASE 只允许 http://127.0.0.1:8000"
            )
        self._token = FREEARK_TOKEN
        self._base = FREEARK_BASE

    def _headers(self) -> dict:
        return {
            "Authorization": f"Token {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, params: dict = None,
                 body: dict = None, timeout: int = 5) -> dict:
        url = f"{self._base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method, headers=self._headers())

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8")
                try:
                    parsed = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    parsed = raw
                return {"success": True, "data": parsed, "http_status": status}
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")[:300]
            except Exception:
                err_body = ""
            return {
                "success": False,
                "error": f"HTTP {e.code}: {err_body}",
                "http_status": e.code,
            }
        except urllib.error.URLError as e:
            return {"success": False, "error": f"连接失败: {e.reason}", "http_status": 0}
        except TimeoutError:
            return {"success": False, "error": f"请求超时（>{timeout}s）", "http_status": 0}
        except Exception as e:
            return {"success": False, "error": f"未知错误: {e}", "http_status": 0}

    def get(self, path: str, params: dict = None, timeout: int = 5) -> dict:
        return self._request("GET", path, params=params, timeout=timeout)

    def post(self, path: str, data: dict, timeout: int = 8) -> dict:
        return self._request("POST", path, body=data, timeout=timeout)

    def log_token_hint(self) -> str:
        return (self._token[:8] + "...") if self._token else "NOT_SET"
