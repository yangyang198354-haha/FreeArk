"""
device_name_cache.py — 设备名称进程内缓存（MOD-BE-UX-01, v0.6.1-FM-UX）

职责：
  - 缓存 DeviceNode.device_sn → DeviceNode.device_name 映射
  - 供 FaultEventSerializer.get_device_name 调用，O(1) 无 IO

设计约束：
  - 不引入 Redis / LocMemCache，使用纯 Python dict
  - TTL = 60s（DeviceNode 几乎不变更，60s 足够）
  - 懒加载：首次调用 get_device_name_by_sn 时触发 _load_cache()（AQ-01 裁决：方案A）
  - 多 worker 说明：若 uvicorn workers > 1，各进程各自维护独立 dict，
    数据一致（DeviceNode 不变），仅各自首次构建，不影响正确性
  - 线程安全：依赖 CPython GIL 保障基本 dict 操作原子性；不加锁（幂等重建）
    ADR-UX-06：最坏情况两个并发请求同时触发 TTL 过期重建——结果幂等，可接受
"""

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模块级缓存状态
# ---------------------------------------------------------------------------

_cache: dict = {}           # key: int(device_sn), value: str(device_name)
_cache_loaded_at: float = 0.0        # 最后加载时间（monotonic）
_TTL_SECONDS: float = 60.0           # 缓存 TTL：60 秒


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def get_device_name_by_sn(sn: int) -> Optional[str]:
    """根据 device_sn（int）查询设备名称。

    自动处理 TTL 过期重建，O(1) dict 查表。
    AQ-01：懒加载方案 A — 首次调用时按需触发 _load_cache()。

    Args:
        sn: 整数设备序列号（FaultEvent.device_sn 转 int 后调用）

    Returns:
        device_name 字符串（如 "新风机"），或 None（未命中）
    """
    _ensure_cache_fresh()
    return _cache.get(sn)


def invalidate_device_name_cache() -> None:
    """手动失效钩子。

    执行后，下次 get_device_name_by_sn 调用将触发 _load_cache() 重建。
    本期（v0.6.1-FM-UX）不接入触发器；预留供未来 device_tree_sync 完成后调用。

    用法示例（device_tree_sync.py 完成后接入）：
        from api.device_name_cache import invalidate_device_name_cache
        invalidate_device_name_cache()
    """
    global _cache_loaded_at
    _cache_loaded_at = 0.0
    logger.info('device_name_cache 已手动失效，下次查询将重建')


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------

def _ensure_cache_fresh() -> None:
    """检查 TTL，过期则重建缓存。"""
    now = time.monotonic()
    if now - _cache_loaded_at > _TTL_SECONDS:
        _load_cache()


def _load_cache() -> None:
    """从 DeviceNode 全量加载 distinct (device_sn, device_name) 到 _cache。

    执行一次 SELECT，量级约 19 条（distinct device_sn），耗时 < 1ms。
    同一 device_sn 在多个 specific_part 下对应同一 device_name（业务上是设备型号），
    OQ-03 裁决：取最先出现的 device_name，key=int(device_sn)，无歧义。
    """
    global _cache, _cache_loaded_at
    try:
        from .models import DeviceNode  # 延迟导入，避免循环引用（AQ-01 懒加载要求）
        pairs = DeviceNode.objects.values_list('device_sn', 'device_name')
        new_cache: dict = {}
        for sn, name in pairs:
            if sn not in new_cache and name:
                new_cache[int(sn)] = name
        _cache = new_cache
        _cache_loaded_at = time.monotonic()
        logger.debug('device_name_cache 重建完成，共 %d 条 distinct device_sn', len(_cache))
    except Exception as exc:
        logger.error('device_name_cache 加载失败: %s', exc, exc_info=True)
        # 失败不崩溃；_cache 保留旧值（可能为空），下次请求再试
        # _cache_loaded_at 保持旧值，使下次请求仍可重试（不设置为 now，避免长时间空缓存）
