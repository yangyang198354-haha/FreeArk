"""
memory_views — 记忆生命周期管理 REST API（MOD-BE-API-MEM, MOD-BE-HIST）

URL 映射（在 urls.py 中注册）：
  GET  /api/memory/me/                                   — 查看自己的会话列表（分页）
  DELETE /api/memory/me/                                 — 清空自己的所有历史记忆
  GET  /api/admin/memory/<user_id>/                      — admin 查看指定用户会话列表
  DELETE /api/admin/memory/<user_id>/                    — admin 清空指定用户历史记忆
  DELETE /api/memory/session/<session_key>/              — 软删除指定会话
  GET  /api/memory/session/<session_key>/history/        — 获取会话历史消息（最近 40 条）

需求引用: REQ-FUNC-017a/b/c, REQ-NFR-010, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008

@module MOD-BE-HIST (SessionHistoryView), MOD-BE-API-MEM (其他视图)
@implements IFC-HIST-001
@depends MOD-BE-MEM (chat_memory)
@author sub_agent_software_developer
"""

import logging
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status

from . import chat_memory

logger = logging.getLogger('api.memory_views')
User = get_user_model()


class MyMemoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        data = chat_memory.get_sessions(request.user, page=page, page_size=page_size)
        return Response(data)

    def delete(self, request):
        deleted = chat_memory.clear_memory(request.user)
        return Response({'deleted_sessions': deleted, 'message': '记忆已清空'})


class AdminMemoryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def _get_target_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def get(self, request, user_id):
        target = self._get_target_user(user_id)
        if target is None:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
        data = chat_memory.get_sessions(target, page=page, page_size=page_size)
        data['target_user'] = target.username
        return Response(data)

    def delete(self, request, user_id):
        target = self._get_target_user(user_id)
        if target is None:
            return Response({'detail': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)
        deleted = chat_memory.clear_memory(target)
        logger.warning(
            'AdminMemoryView: admin=%s 清空了 user_id=%s (%s) 的记忆，删除 %d 个会话',
            request.user.username, user_id, target.username, deleted,
        )
        return Response({
            'deleted_sessions': deleted,
            'target_user': target.username,
            'message': f'用户 {target.username} 的记忆已清空',
        })


class SessionDeleteView(APIView):
    """
    @module MOD-BE-04
    @implements IFC-BE-04-01, IFC-BE-04-02
    @depends MOD-BE-02 (soft_delete_session)
    @author sub_agent_software_developer

    DELETE /api/memory/session/{session_key}/ — 软删除指定会话。
    归属校验由 chat_memory.soft_delete_session 保证，本视图不可跨用户删除。
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_key):
        try:
            chat_memory.soft_delete_session(request.user, session_key)
        except ValueError:
            return Response(
                {'detail': '会话不存在或无权限删除'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'message': '会话已删除', 'session_key': session_key})


class SessionHistoryView(APIView):
    """
    GET /api/memory/session/{session_key}/history/ — 获取会话历史消息（最近 40 条，升序）。

    权限：IsAuthenticated（DRF Token 认证），仅允许归属用户访问。
    路径参数：session_key — 完整 UUID 字符串
    响应：{ session_key, messages: [{role, content, created_at}], total }
    错误：404 — session_key 不存在或不属于当前用户

    @module MOD-BE-HIST
    @implements IFC-HIST-001
    @depends MOD-BE-MEM (get_session_history)
    @author sub_agent_software_developer
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, session_key):
        try:
            messages = chat_memory.get_session_history(
                request.user, session_key, limit=40
            )
        except ValueError:
            return Response(
                {'detail': '会话不存在或无权限访问'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            'session_key': session_key,
            'messages': messages,
            'total': len(messages),
        })
