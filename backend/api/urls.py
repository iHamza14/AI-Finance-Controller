from django.urls import path
from .views import UploadAndStartReconciliationView, JobStatusView, DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path('reconcile/start/', UploadAndStartReconciliationView.as_view(), name='reconcile-start'),
    path('reconcile/status/<uuid:job_id>/', JobStatusView.as_view(), name='reconcile-status'),
]
