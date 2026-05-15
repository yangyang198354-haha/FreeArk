"""设备树同步服务。

负责：
  1) 通过 OwnerInfo.unique_id (screenMAC) 调用屏侧 floor-room-device/list 接口。
  2) 把返回的 Floor → Room → Device → Attr 树落到本地 5 张表（事务幂等 upsert）。
  3) 支持批量异步任务：进程内 dict 存任务状态，线程池并发执行。

注意：使用 stdlib（urllib + threading），无新增依赖。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from django.db import transaction

from .models import (
    DeviceAttrBinding,
    DeviceAttrDef,
    DeviceFloor,
    DeviceNode,
    DeviceRoom,
    OwnerInfo,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
REMOTE_BASE_URL = 'http://47.117.41.184:10013'
REMOTE_PATH = '/homeauto-contact-screen/contact-screen/screen/floor-room-device/list'
REMOTE_TIMEOUT_SECONDS = 10
REMOTE_RETRY = 1  # 失败重试次数

BATCH_MAX_WORKERS = 4         # 批量同步并发数
BATCH_PER_HOUSE_INTERVAL = 0.1  # 单户调用之间至少间隔 100ms（节流，避免压垮远端）

# 进程内任务表（按 Q8 决定）：{task_id: TaskInfo}
_TASKS: Dict[str, Dict[str, Any]] = {}
_TASKS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------
class SyncError(Exception):
    """同步过程业务异常基类。"""

    def __init__(self, message: str, http_status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


class MissingScreenMacError(SyncError):
    def __init__(self, specific_part: str) -> None:
        super().__init__(f'户 {specific_part} 未绑定 screenMAC', http_status=400)


class OwnerNotFoundError(SyncError):
    def __init__(self, specific_part: str) -> None:
        super().__init__(f'未找到户 {specific_part}', http_status=404)


# ---------------------------------------------------------------------------
# 1. 远程调用
# ---------------------------------------------------------------------------
def call_remote_floor_room_device_list(screen_mac: str) -> dict:
    """调用屏侧接口，返回 JSON dict。失败抛 SyncError。"""
    url = f'{REMOTE_BASE_URL}{REMOTE_PATH}'
    last_err: Optional[Exception] = None
    for attempt in range(REMOTE_RETRY + 1):
        try:
            req = urllib_request.Request(
                url,
                data=b'',
                method='POST',
                headers={
                    'screenMAC': screen_mac,
                    'Content-Type': 'application/json',
                    'Content-Length': '0',
                },
            )
            with urllib_request.urlopen(req, timeout=REMOTE_TIMEOUT_SECONDS) as resp:
                raw = resp.read().decode('utf-8')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise SyncError('远程返回 JSON 结构异常（非对象）', http_status=502)
            code = data.get('code')
            if code != 200:
                raise SyncError(
                    f'远程业务码异常: code={code} message={data.get("message")}',
                    http_status=502,
                )
            return data
        except HTTPError as e:
            last_err = e
            logger.warning(
                'floor-room-device/list HTTPError mac=%s attempt=%d status=%s',
                screen_mac, attempt, e.code,
            )
        except (URLError, TimeoutError) as e:
            last_err = e
            logger.warning(
                'floor-room-device/list URLError mac=%s attempt=%d err=%s',
                screen_mac, attempt, e,
            )
        except json.JSONDecodeError as e:
            last_err = e
            logger.warning(
                'floor-room-device/list JSONDecodeError mac=%s attempt=%d err=%s',
                screen_mac, attempt, e,
            )
    raise SyncError(f'远程调用失败: {last_err}', http_status=502)


# ---------------------------------------------------------------------------
# 2. Upsert 落库
# ---------------------------------------------------------------------------
def _to_int_or_none(v: Any) -> Optional[int]:
    if v is None or v == '':
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _attr_def_payload(attr: dict) -> Tuple[str, dict]:
    """返回 (attr_tag, defaults_for_upsert)。"""
    select_values = attr.get('selectValues') or []
    num_value = attr.get('numValue')
    return attr['attrTag'], {
        'attr_value_type': int(attr.get('attrValueType') or 0),
        'attr_constraint': int(attr.get('attrConstraint') or 0),
        'select_values_json': json.dumps(select_values, ensure_ascii=False),
        'num_value_json': json.dumps(num_value, ensure_ascii=False) if num_value is not None else '',
    }


@transaction.atomic
def upsert_tree(owner: OwnerInfo, data_payload: List[dict], prune: bool = False) -> Dict[str, int]:
    """把远程返回的 data 数组落库。返回统计 dict。

    Args:
        owner: 已存在的业主记录
        data_payload: 远程响应的 ``data`` 数组（楼层列表）
        prune: True 时把远程未出现的子节点删除；默认 False（保留旧记录）
    """
    stats = {
        'floors': 0,
        'rooms': 0,
        'devices': 0,
        'attr_defs_total': 0,
        'attr_defs_new': 0,
        'bindings': 0,
    }
    seen_floor_ids: List[int] = []
    seen_room_ids: List[int] = []
    seen_device_ids: List[int] = []

    for floor in data_payload or []:
        floor_no = _to_int_or_none(floor.get('floor'))
        if floor_no is None:
            continue
        floor_obj, _ = DeviceFloor.objects.update_or_create(
            owner=owner,
            floor_no=floor_no,
            defaults={'floor_name': str(floor.get('floorName') or '')},
        )
        seen_floor_ids.append(floor_obj.id)
        stats['floors'] += 1

        for room in floor.get('rooms') or []:
            ori_name = str(room.get('oriRoomName') or room.get('roomName') or '')
            if not ori_name:
                continue
            room_obj, _ = DeviceRoom.objects.update_or_create(
                floor=floor_obj,
                ori_room_name=ori_name,
                defaults={
                    'room_name': str(room.get('roomName') or ori_name),
                    'room_type': int(room.get('roomType') or 0),
                },
            )
            seen_room_ids.append(room_obj.id)
            stats['rooms'] += 1

            for device in room.get('devices') or []:
                device_sn = _to_int_or_none(device.get('deviceSn'))
                if device_sn is None:
                    continue
                proto = device.get('deviceProtocol') or {}
                node_defaults = {
                    'device_name': str(device.get('deviceName') or ''),
                    'system_flag': int(device.get('systemFlag') or 0),
                    'related_device_sn': _to_int_or_none(device.get('relatedDeviceSn')),
                    'product_code': str(device.get('productCode') or ''),
                    'category_code': int(device.get('categoryCode') or 0),
                    'protocol': _to_int_or_none(proto.get('protocol')),
                    'address_code': _to_int_or_none(proto.get('addressCode')),
                }
                device_obj, _ = DeviceNode.objects.update_or_create(
                    room=room_obj,
                    device_sn=device_sn,
                    defaults=node_defaults,
                )
                seen_device_ids.append(device_obj.id)
                stats['devices'] += 1

                # ---- Attr 定义 + 绑定 ----
                product_code = node_defaults['product_code']
                attr_def_ids_for_device: List[int] = []
                for attr in device.get('attrs') or []:
                    attr_tag, defaults = _attr_def_payload(attr)
                    if not attr_tag:
                        continue
                    attr_def_obj, created = DeviceAttrDef.objects.update_or_create(
                        product_code=product_code,
                        attr_tag=attr_tag,
                        defaults=defaults,
                    )
                    if created:
                        stats['attr_defs_new'] += 1
                    attr_def_ids_for_device.append(attr_def_obj.id)
                stats['attr_defs_total'] += len(attr_def_ids_for_device)

                # 重建该设备的 attr 绑定（删除当前设备旧绑定后批量插入）
                DeviceAttrBinding.objects.filter(device=device_obj).delete()
                bindings = [
                    DeviceAttrBinding(device_id=device_obj.id, attr_def_id=def_id)
                    for def_id in attr_def_ids_for_device
                ]
                DeviceAttrBinding.objects.bulk_create(bindings, ignore_conflicts=True)
                stats['bindings'] += len(bindings)

    if prune:
        # 仅清理本次未出现的同 owner 下旧节点（级联删除房间/设备/绑定）
        DeviceRoom.objects.filter(
            floor__owner=owner
        ).exclude(id__in=seen_room_ids).delete()
        DeviceFloor.objects.filter(
            owner=owner
        ).exclude(id__in=seen_floor_ids).delete()

    return stats


# ---------------------------------------------------------------------------
# 3. 单户同步入口
# ---------------------------------------------------------------------------
def sync_one_specific_part(specific_part: str, prune: bool = False) -> Dict[str, Any]:
    """同步单户，返回 {stats, screen_mac, specific_part}。"""
    try:
        owner = OwnerInfo.objects.get(specific_part=specific_part)
    except OwnerInfo.DoesNotExist as e:
        raise OwnerNotFoundError(specific_part) from e

    screen_mac = (owner.unique_id or '').strip()
    if not screen_mac:
        raise MissingScreenMacError(specific_part)

    payload = call_remote_floor_room_device_list(screen_mac)
    data_list = payload.get('data') or []
    if not isinstance(data_list, list):
        raise SyncError('远程返回 data 字段不是数组', http_status=502)

    stats = upsert_tree(owner, data_list, prune=prune)
    return {
        'specific_part': specific_part,
        'screen_mac': screen_mac,
        'stats': stats,
    }


# ---------------------------------------------------------------------------
# 4. 批量异步任务
# ---------------------------------------------------------------------------
def _new_task_record(total: int, specific_parts: List[str]) -> str:
    task_id = uuid.uuid4().hex
    with _TASKS_LOCK:
        _TASKS[task_id] = {
            'task_id': task_id,
            'status': 'pending',   # pending | running | finished | failed
            'total': total,
            'processed': 0,
            'success': 0,
            'failed': 0,
            'errors': [],          # [{specific_part, message}]
            'pending': list(specific_parts),
            'started_at': None,
            'finished_at': None,
            'updated_at': datetime.utcnow().isoformat() + 'Z',
        }
    return task_id


def _update_task(task_id: str, **updates: Any) -> None:
    with _TASKS_LOCK:
        record = _TASKS.get(task_id)
        if record is None:
            return
        record.update(updates)
        record['updated_at'] = datetime.utcnow().isoformat() + 'Z'


def get_task_status(task_id: str) -> Optional[dict]:
    with _TASKS_LOCK:
        record = _TASKS.get(task_id)
        if record is None:
            return None
        # 返回浅拷贝（避免外部修改影响内部状态）
        return {k: v for k, v in record.items() if k != 'pending'}


def _run_batch_task(task_id: str, specific_parts: List[str], prune: bool) -> None:
    _update_task(task_id, status='running', started_at=datetime.utcnow().isoformat() + 'Z')

    # 用线程池并发；每户处理后 sleep BATCH_PER_HOUSE_INTERVAL 节流
    def _worker(sp: str) -> Tuple[str, Optional[str]]:
        try:
            sync_one_specific_part(sp, prune=prune)
            return sp, None
        except SyncError as e:
            return sp, e.message
        except Exception as e:  # noqa: BLE001 — 兜底，避免线程挂死
            logger.exception('batch sync unexpected error sp=%s', sp)
            return sp, f'未预期错误: {e}'

    # 使用 with 上下文 + map 不便插入节流，改为手工 submit + as_completed-style 逐次推进
    with ThreadPoolExecutor(max_workers=BATCH_MAX_WORKERS) as executor:
        futures = []
        for sp in specific_parts:
            futures.append(executor.submit(_worker, sp))
            time.sleep(BATCH_PER_HOUSE_INTERVAL)
        for fut in futures:
            sp, err = fut.result()
            with _TASKS_LOCK:
                record = _TASKS.get(task_id)
                if record is None:
                    continue
                record['processed'] += 1
                if err is None:
                    record['success'] += 1
                else:
                    record['failed'] += 1
                    record['errors'].append({'specific_part': sp, 'message': err})
                record['updated_at'] = datetime.utcnow().isoformat() + 'Z'

    _update_task(
        task_id,
        status='finished',
        finished_at=datetime.utcnow().isoformat() + 'Z',
    )


def start_batch_sync(specific_parts: Iterable[str], prune: bool = False) -> Tuple[str, int]:
    """创建并启动一个批量同步任务。

    Returns:
        (task_id, total)
    """
    sp_list = [sp.strip() for sp in specific_parts if sp and sp.strip()]
    task_id = _new_task_record(total=len(sp_list), specific_parts=sp_list)
    thread = threading.Thread(
        target=_run_batch_task,
        args=(task_id, sp_list, prune),
        name=f'device-tree-batch-sync-{task_id[:8]}',
        daemon=True,
    )
    thread.start()
    return task_id, len(sp_list)
