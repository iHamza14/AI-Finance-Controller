from django.urls import path
from .views import UploadAndStartReconciliationView, JobStatusView

urlpatterns = [
    path('reconcile/start/', UploadAndStartReconciliationView.as_view(), name='reconcile-start'),
    path('reconcile/status/<uuid:job_id>/', JobStatusView.as_view(), name='reconcile-status'),
]
