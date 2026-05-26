"""
memory_views — 记忆生命周期管理 REST API（MOD-BE-API-MEM）

URL 映射（在 urls.py 中注册）：
  GET  /api/memory/me/                 — 查看自己的会话列表（分页）
  DELETE /api/memory/me/               — 清空自己的所有历史记忆
  GET  /api/admin/memory/<user_id>/    — admin 查看指定用户会话列表
  DELETE /api/admin/memory/<user_id>/  — admin 清空指定用户历史记忆

需求引用: REQ-FUNC-017a/b/c, REQ-NFR-010
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
