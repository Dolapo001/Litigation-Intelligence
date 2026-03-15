from rest_framework import serializers
from app.storage.models import Filing, IngestionLog


class FilingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Filing
        fields = [
            "id",
            "docket_id",
            "court",
            "case_name",
            "plaintiff",
            "defendant",
            "summary",
            "pdf_path",
            "date_filed",
            "created_at",
        ]


class IngestionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionLog
        fields = ["id", "docket_id", "status", "message", "created_at"]
