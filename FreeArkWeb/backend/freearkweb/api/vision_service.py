"""
api.vision_service — doubao-vision VLM 调用封装 + 进程内临时图片存储

职责：
  1. 进程内临时图片存储（dict + TTL 惰性清理 + 50MB 总量上限）
  2. doubao-vision VLM 分析（AsyncOpenAI，超时/重试/降级）
  3. 安全约束：base64 字节绝不进任何 logger 调用

架构决策锚定：
  - ADR-MQ-001：VLM 调用在 adapter 层外置（本模块只提供调用接口）
  - ADR-MQ-002：进程内 dict 存储，无 Django CACHES 依赖
  - REQ-NFR-003 SC-002：日志中绝不出现 image_bytes 或 base64 字符串

@module MOD-MQ-03
@implements IFC-MQ-03-001 (store_upload), IFC-MQ-03-002 (get_upload),
            IFC-MQ-03-003 (check_capacity), IFC-MQ-03-004 (delete_upload),
            IFC-MQ-03-005 (analyze_image)
@depends 外部: doubao-vision API（火山方舟）
@author sub_agent_software_developer
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("api.vision_service")

# ── 发往 VLM 前的图片预处理上限 ───────────────────────────────────────────────────
# v1.5.0 上线后实测修复：doubao-vision 对大图推理慢 + Pi WiFi 上传慢，原图直发易超
# timeout（11MB 图两次 30s 尝试均超时 → VisionServiceError "图片分析暂时不可用"）。
# 缩到最长边 <= _VLM_MAX_EDGE 且重编码 JPEG 后 payload 由 MB 级降到百 KB 级，
# 单次推理约 10s 内完成。
_VLM_MAX_EDGE = 1536                      # 最长边像素上限，超过则等比缩小
_VLM_JPEG_QUALITY = 85                    # 缩放/重编码后的 JPEG 质量
_VLM_MAX_BYTES = 1536 * 1024             # 即使尺寸不大，字节超此值也重编码压缩


def _downscale_for_vlm(image_bytes: bytes) -> bytes:
    """把过大的图片等比缩小 + 重编码为 JPEG，控制发往 VLM 的 payload 体积。

    触发条件：最长边 > _VLM_MAX_EDGE，或原始字节 > _VLM_MAX_BYTES。
    任何失败（Pillow 不可用 / 非图片字节 / 解码异常）都退回原始字节，绝不阻断调用。
    安全约束：日志中只打尺寸与字节数，绝不打图片内容。
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as im:
            im = im.convert("RGB")
            w, h = im.size
            need_resize = max(w, h) > _VLM_MAX_EDGE
            need_recompress = len(image_bytes) > _VLM_MAX_BYTES
            if not need_resize and not need_recompress:
                return image_bytes
            if need_resize:
                im.thumbnail((_VLM_MAX_EDGE, _VLM_MAX_EDGE), Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=_VLM_JPEG_QUALITY, optimize=True)
            result = out.getvalue()
        logger.info(
            "vision_service._downscale_for_vlm: %dx%d %dB -> JPEG %dB",
            w, h, len(image_bytes), len(result),
        )
        return result
    except Exception as exc:
        logger.warning(
            "vision_service._downscale_for_vlm: 跳过缩放（退回原图）: %s",
            type(exc).__name__,
        )
        return image_bytes

# ── 异常类 ─────────────────────────────────────────────────────────────────────

class VisionServiceError(Exception):
    """VLM 调用最终失败（超时/5xx，最大重试次数均失败后抛出）。"""
    pass


class ImageExpiredError(Exception):
    """upload_id 对应的图片已过期或不存在。"""
    pass


class ImageAccessDeniedError(Exception):
    """upload_id 存在但 user_id 不匹配，拒绝访问。"""
    pass


class StorageCapacityError(Exception):
    """进程内临时存储已达上限（VISION_UPLOAD_MAX_TOTAL_MB），拒绝新上传。"""
    pass


# ── 进程内临时存储（模块级全局变量，ADR-MQ-002）─────────────────────────────────
# 结构：{ upload_id: { "user_id": int, "bytes": bytes, "expire_at": datetime, "size": int } }
_upload_store: dict = {}
_total_size: int = 0          # 当前总占用字节数（惰性清理后实时更新）
_store_lock = threading.Lock()  # 保护复合读写操作（REST sync 线程 + ASGI 协程均可调用）


def _get_vision_config():
    """惰性读取 Django settings 中的 VLM 配置（避免模块 import 时 Django 未就绪）。"""
    from django.conf import settings
    return {
        "model": getattr(settings, "DOUBAO_VISION_MODEL", "doubao-vision-lite-32k"),
        "base_url": getattr(settings, "DOUBAO_VISION_BASE_URL",
                           "https://ark.cn-beijing.volces.com/api/v3"),
        "api_key": getattr(settings, "DOUBAO_API_KEY", ""),
        "timeout": getattr(settings, "DOUBAO_VISION_TIMEOUT", 30),
        "max_retries": getattr(settings, "DOUBAO_VISION_MAX_RETRIES", 1),
        "upload_ttl": getattr(settings, "VISION_UPLOAD_TTL", 600),
        "max_total_mb": getattr(settings, "VISION_UPLOAD_MAX_TOTAL_MB", 50),
        # v1.6.0 新增：多图批量分析整体超时（RISK-MI-002）
        "batch_timeout": getattr(settings, "VISION_BATCH_TIMEOUT_SECONDS", 90),
    }


# ── 存储接口（同步，线程安全）───────────────────────────────────────────────────

def store_upload(image_bytes: bytes, user_id: int) -> str:
    """
    将图片字节存入进程内临时存储，返回 upload_id（UUID4 字符串）。

    前置检查：当前总量 + 本次字节 > 上限 → raise StorageCapacityError
    TTL：expire_at = 当前时间 + VISION_UPLOAD_TTL 秒
    _total_size 同步更新（+= size）

    日志：INFO 记录 upload_id、user_id、size（不含图片内容）
    """
    global _total_size
    cfg = _get_vision_config()
    max_bytes = cfg["max_total_mb"] * 1024 * 1024
    ttl_seconds = cfg["upload_ttl"]
    size = len(image_bytes)

    with _store_lock:
        # 惰性过期清理（先清再判，最大化可用空间）
        _evict_expired_locked()

        if _total_size + size > max_bytes:
            logger.warning(
                "vision_service.store_upload: 存储已满，拒绝上传 user_id=%s size=%d total=%d max=%d",
                user_id, size, _total_size, max_bytes,
            )
            raise StorageCapacityError(
                f"临时存储已满（当前 {_total_size // 1024 // 1024}MB，上限 {cfg['max_total_mb']}MB）"
            )

        upload_id = str(uuid.uuid4())
        expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        _upload_store[upload_id] = {
            "user_id": user_id,
            "bytes": image_bytes,
            "expire_at": expire_at,
            "size": size,
        }
        _total_size += size

    logger.info(
        "vision_service.store_upload: upload_id=%s user_id=%s size=%d ttl=%ds",
        upload_id, user_id, size, ttl_seconds,
    )
    return upload_id


def get_upload(upload_id: str, user_id: int) -> bytes:
    """
    从临时存储取回图片字节。

    - upload_id 不在 _upload_store 中 → raise ImageExpiredError
    - entry["expire_at"] < utcnow() → 惰性清理，raise ImageExpiredError
    - entry["user_id"] != user_id → raise ImageAccessDeniedError
    - 成功后不删除（允许 TTL 内多次取用；adapter 在 VLM 完成后调用 delete_upload 手动释放）

    返回：bytes（图片原始字节）
    """
    global _total_size
    with _store_lock:
        entry = _upload_store.get(upload_id)
        if entry is None:
            raise ImageExpiredError(f"upload_id={upload_id} 不存在或已过期")

        if datetime.utcnow() > entry["expire_at"]:
            # 惰性清理已过期条目
            _total_size -= entry["size"]
            del _upload_store[upload_id]
            raise ImageExpiredError(f"upload_id={upload_id} 已过期（TTL 超限）")

        if entry["user_id"] != user_id:
            raise ImageAccessDeniedError(
                f"upload_id={upload_id} 不属于 user_id={user_id}"
            )

        return entry["bytes"]


def check_capacity() -> bool:
    """
    返回 True 表示有剩余容量可接受新上传；False 表示已达上限。
    同时执行惰性过期清理（释放已过期条目，更新计数）。
    """
    global _total_size
    cfg = _get_vision_config()
    max_bytes = cfg["max_total_mb"] * 1024 * 1024
    with _store_lock:
        _evict_expired_locked()
        return _total_size < max_bytes


def delete_upload(upload_id: str) -> None:
    """
    手动删除指定 upload_id（VLM 调用完成后释放，可选调用）。
    若不存在或已过期，静默忽略。
    """
    global _total_size
    with _store_lock:
        entry = _upload_store.pop(upload_id, None)
        if entry is not None:
            _total_size -= entry["size"]
    # 不记录日志（频繁调用，避免日志噪音）


def _evict_expired_locked() -> None:
    """
    清理 _upload_store 中所有已过期条目，更新 _total_size。
    必须在持有 _store_lock 时调用（内部函数，无自加锁）。
    """
    global _total_size
    now = datetime.utcnow()
    expired_keys = [
        k for k, v in _upload_store.items() if now > v["expire_at"]
    ]
    for k in expired_keys:
        _total_size -= _upload_store[k]["size"]
        del _upload_store[k]
    if expired_keys:
        logger.info(
            "vision_service: 惰性清理 %d 条过期上传记录，当前总量 %d bytes",
            len(expired_keys), _total_size,
        )


# ── VLM 分析接口（异步）──────────────────────────────────────────────────────────

async def analyze_image(image_bytes: bytes, user_text: str) -> str:
    """
    调用 doubao-vision VLM 分析图片，返回文字描述。

    调用格式：openai-compatible multimodal（data:image/jpeg;base64,...）
    超时：asyncio.timeout(settings.DOUBAO_VISION_TIMEOUT) 默认 30s
    重试：超时/5xx 时等待 2s 指数退避，重试最多 settings.DOUBAO_VISION_MAX_RETRIES 次
    4xx：不重试（客户端错误，直接 raise VisionServiceError）
    最终失败：raise VisionServiceError

    安全约束（REQ-NFR-003 SC-002）：
      - logger 调用中绝不出现 image_bytes 或 b64_str 参数
      - b64_str 在 payload 构造后不另存引用，函数返回前确保 del

    返回：str，VLM 描述文字，非空
    """
    cfg = _get_vision_config()
    model = cfg["model"]
    base_url = cfg["base_url"]
    api_key = cfg["api_key"]
    timeout_secs = cfg["timeout"]
    max_retries = cfg["max_retries"]

    prompt = user_text.strip() if user_text.strip() else (
        "请描述这张图片的内容，包括图中的文字、数字、设备型号、状态等关键信息。"
    )

    # 发送前等比缩小 + 重编码，避免大图超时（v1.5.0 上线后修复）
    image_bytes = _downscale_for_vlm(image_bytes)
    size = len(image_bytes)
    logger.info("vision_service.analyze_image: start size=%d bytes (post-downscale)", size)

    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    last_error: Optional[Exception] = None
    attempt = 0

    while attempt <= max_retries:
        start_ts = time.monotonic()
        try:
            # base64 编码：在局部作用域内构造，不赋给持久引用
            b64_str = base64.b64encode(image_bytes).decode("utf-8")

            async with asyncio.timeout(timeout_secs):
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64_str}"
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                )

            # 调用成功，立即销毁 b64_str（REQ-NFR-002 内存释放）
            del b64_str

            elapsed = time.monotonic() - start_ts
            description = (
                response.choices[0].message.content or ""
            ).strip()

            if not description:
                logger.warning(
                    "vision_service.analyze_image: VLM 返回空描述 attempt=%d elapsed=%.2fs",
                    attempt + 1, elapsed,
                )
                description = "（图片内容无法识别）"

            logger.info(
                "vision_service.analyze_image: success attempt=%d elapsed=%.2fs desc_len=%d",
                attempt + 1, elapsed, len(description),
            )
            return description

        except asyncio.TimeoutError as exc:
            elapsed = time.monotonic() - start_ts
            last_error = exc
            logger.warning(
                "vision_service.analyze_image: timeout attempt=%d elapsed=%.2fs, %s",
                attempt + 1, elapsed,
                "retrying" if attempt < max_retries else "giving up",
            )
            # 确保 b64_str 不持有（超时时可能未执行 del）
            try:
                del b64_str  # noqa: F821
            except NameError:
                pass

        except Exception as exc:
            elapsed = time.monotonic() - start_ts
            # 4xx 错误：不重试
            status_code = getattr(exc, "status_code", None)
            is_4xx = (status_code is not None and 400 <= status_code < 500)

            try:
                del b64_str  # noqa: F821
            except NameError:
                pass

            if is_4xx:
                logger.error(
                    "vision_service.analyze_image: 4xx error attempt=%d elapsed=%.2fs type=%s",
                    attempt + 1, elapsed, type(exc).__name__,
                )
                raise VisionServiceError(
                    f"VLM 调用被拒绝（{status_code}），请联系管理员检查 API 配置"
                ) from exc

            last_error = exc
            logger.warning(
                "vision_service.analyze_image: error attempt=%d elapsed=%.2fs type=%s, %s",
                attempt + 1, elapsed, type(exc).__name__,
                "retrying" if attempt < max_retries else "giving up",
            )

        attempt += 1
        if attempt <= max_retries:
            # 指数退避：2s 起始（首次重试等 2s，第二次等 4s…）
            wait = 2 * (2 ** (attempt - 1))
            await asyncio.sleep(wait)

    # 全部尝试均失败
    logger.error(
        "vision_service.analyze_image: failed after %d attempts: %s",
        max_retries + 1, type(last_error).__name__,
    )
    raise VisionServiceError(
        "图片分析暂时不可用，您可以用文字描述图片内容后重试"
    ) from last_error


# ── 多图批量分析接口（v1.6.0 新增，MOD-MI-03）────────────────────────────────────

async def analyze_images_batch(
    image_bytes_list: list,
    user_text: str,
    on_progress=None,
) -> list:
    """
    批量分析多张图片，逐图独立调用 analyze_image，返回有序结果列表。

    参数：
      image_bytes_list: 图片字节列表（list[bytes]），顺序与 upload_ids 保持一致（REQ-MI-004）
                        安全约束：不进任何 logger 调用，日志只记录 index 和 size
      user_text: 用户原始文字（可为空）；对每张图使用相同的 user_text
      on_progress: 可选的进度回调（异步，Callable[[int, int], Awaitable[None]]）
                   每张图开始分析前调用，参数 (index: int, total: int)

    行为（ADR-MI-001：逐图独立调用，asyncio.gather with return_exceptions=True）：
      1. 整体用 asyncio.timeout(VISION_BATCH_TIMEOUT_SECONDS) 包裹（默认90s，RISK-MI-002）
      2. 对每张图创建 task_with_progress wrapper：先调用 on_progress，再调用 analyze_image
      3. asyncio.gather(*tasks, return_exceptions=True) 并发执行
      4. 聚合结果：成功(str) → results[i] = description；失败(Exception) → results[i] = None

    返回：list[str | None]，长度等于 image_bytes_list 长度，顺序对应（REQ-MI-004）

    异常：
      - asyncio.TimeoutError（整体90s超时）→ 直接抛出（由 adapter 包装为 VisionServiceError）
      - 不抛 VisionServiceError（单图失败通过 return_exceptions=True 收集为 None）

    日志约束（继承 SC-002）：
      - INFO: "analyze_images_batch: start count={N}"
      - INFO: "analyze_images_batch: done success={S} failed={F} elapsed={t:.2f}s"
      - 绝不记录 image_bytes 或 base64 字符串

    @module MOD-MI-03
    @since v1.6.0
    """
    cfg = _get_vision_config()
    batch_timeout = cfg.get("batch_timeout", 90)
    total = len(image_bytes_list)

    logger.info("vision_service.analyze_images_batch: start count=%d", total)
    start_ts = time.monotonic()

    async def _task_wrapper(index: int, img: bytes):
        """每张图的 wrapper：先发进度回调，再调用 analyze_image。"""
        # 安全约束：不记录 img 内容，只记录 index 和 size
        logger.info(
            "vision_service.analyze_images_batch: index=%d size=%d bytes",
            index, len(img),
        )
        if on_progress is not None:
            try:
                await on_progress(index, total)
            except Exception as cb_exc:  # noqa: BLE001
                # 进度回调失败不影响 VLM 调用（非阻塞）
                logger.warning(
                    "vision_service.analyze_images_batch: on_progress[%d] 失败（忽略）: %s",
                    index, type(cb_exc).__name__,
                )
        return await analyze_image(img, user_text)

    tasks = [_task_wrapper(i, img) for i, img in enumerate(image_bytes_list)]

    try:
        async with asyncio.timeout(batch_timeout):
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_ts
        logger.error(
            "vision_service.analyze_images_batch: 整体超时 elapsed=%.2fs batch_timeout=%ds",
            elapsed, batch_timeout,
        )
        raise  # 由 adapter 层处理

    # 聚合：成功 → str；异常 → None
    results = []
    success_count = 0
    fail_count = 0
    for r in raw_results:
        if isinstance(r, Exception):
            results.append(None)
            fail_count += 1
        else:
            results.append(r)
            success_count += 1

    elapsed = time.monotonic() - start_ts
    logger.info(
        "vision_service.analyze_images_batch: done success=%d failed=%d elapsed=%.2fs",
        success_count, fail_count, elapsed,
    )
    return results
