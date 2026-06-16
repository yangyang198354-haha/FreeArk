"""
api.serializers_rag — RAG 知识库序列化器（v1.4.0_sanheng_rag）
"""

from rest_framework import serializers
from .models_rag import RagDocument


class RagDocumentSerializer(serializers.ModelSerializer):
    """
    RagDocument 只读序列化器：用于 list/create/retry 响应。
    uploaded_by 返回用户名字符串（用户已删则返回空串）。
    """

    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = RagDocument
        fields = [
            'id',
            'file_name',
            'file_size',
            'uploaded_by',
            'status',
            'chunk_count',
            'error_message',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_uploaded_by(self, obj):
        if obj.uploaded_by is None:
            return ''
        return obj.uploaded_by.username
