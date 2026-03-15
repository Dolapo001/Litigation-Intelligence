from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from app.storage.models import Filing, IngestionLog
from .serializers import FilingSerializer, IngestionLogSerializer


class LatestFilingsView(APIView):
    """
    GET /api/filings/latest
    Returns the most recently ingested filings (default: last 20).
    """

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 20)), 100)
        filings = Filing.objects.all()[:limit]
        serializer = FilingSerializer(filings, many=True)
        return Response(serializer.data)


class FilingDetailView(APIView):
    """
    GET /api/filings/<docket_id>/
    Returns a single filing by docket ID.
    """

    def get(self, request, docket_id):
        try:
            filing = Filing.objects.get(docket_id=docket_id)
        except Filing.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = FilingSerializer(filing)
        return Response(serializer.data)


class IngestionLogsView(APIView):
    """
    GET /api/ingestion/logs/
    Returns recent ingestion log entries for monitoring.
    """

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 50)), 200)
        logs = IngestionLog.objects.all()[:limit]
        serializer = IngestionLogSerializer(logs, many=True)
        return Response(serializer.data)


class HealthCheckView(APIView):
    """
    GET /api/health/
    Simple health check endpoint.
    """

    def get(self, request):
        count = Filing.objects.count()
        return Response({"status": "ok", "filings_in_db": count})
