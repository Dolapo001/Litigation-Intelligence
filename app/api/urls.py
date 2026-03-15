from django.urls import path
from .views import (
    LatestFilingsView,
    FilingDetailView,
    IngestionLogsView,
    HealthCheckView,
)

urlpatterns = [
    path("filings/latest/", LatestFilingsView.as_view(), name="filings-latest"),
    path("filings/<str:docket_id>/", FilingDetailView.as_view(), name="filing-detail"),
    path("ingestion/logs/", IngestionLogsView.as_view(), name="ingestion-logs"),
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
