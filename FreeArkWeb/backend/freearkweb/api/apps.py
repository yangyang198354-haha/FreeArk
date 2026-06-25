import logging

from django.apps import AppConfig

logger = logging.getLogger('api.apps')


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        # 预热 LangGraph 编排器，使图编译/模型构造在 worker 启动时一次性付清，
        # 避免首个聊天请求承担冷启动。预热失败仅记日志、不阻断启动。
        #
        # 测试期必须跳过：warm() 会构造并缓存编排器单例 _ORCH（adapter._get_orch），
        # 这发生在 AppConfig.ready()——早于任何用例的 @override_settings
        # (LANGGRAPH_USE_FAKE_LLM=True 等) 生效；若不跳过，依赖 fake-LLM 确定性行为的
        # 用例（写确认门 OrchestratorWriteGate / WriteDelegationGate）会拿到用启动期真实
        # 配置构造的陈旧单例而失败。v1.7.0 退役 OpenClaw 前由 `CHAT_BACKEND!='langgraph'`
        # 守卫顺带跳过；退役后该守卫移除，故此处显式按"是否在跑测试"跳过。
        import sys
        if 'test' in sys.argv or 'pytest' in sys.modules:
            return
        try:
            from api.langgraph_chat.adapter import warm
            warm()
        except Exception as exc:  # noqa: BLE001
            logger.warning('LangGraph 预热入口异常（忽略，运行期重试）: %s', exc)
