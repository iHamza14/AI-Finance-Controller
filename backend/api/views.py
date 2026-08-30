from django.views.generic import TemplateView
import os
import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import ReconciliationJob
from .serializers import ReconciliationJobSerializer
from .tasks import run_reconciliation_pipeline
from django.core.files.storage import FileSystemStorage
from django.conf import settings

class UploadAndStartReconciliationView(APIView):
    def post(self, request):
        if 'bank_statements' not in request.FILES or 'gl_ledger' not in request.FILES or 'invoices' not in request.FILES:
            return Response(
                {"error": "Please provide bank_statements, gl_ledger, and invoices files."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        job_id = uuid.uuid4()
        # Save to project root / data / job_id
        run_dir = os.path.join(settings.BASE_DIR.parent, "data", str(job_id))
        os.makedirs(run_dir, exist_ok=True)
        
        fs = FileSystemStorage(location=run_dir)
        fs.save('bank_statements.csv', request.FILES['bank_statements'])
        fs.save('gl_ledger.csv', request.FILES['gl_ledger'])
        fs.save('invoices.csv', request.FILES['invoices'])
        
        job = ReconciliationJob.objects.create(id=job_id, status='PENDING')
        run_reconciliation_pipeline.delay(str(job_id), run_dir)
        
        return Response(ReconciliationJobSerializer(job).data, status=status.HTTP_201_CREATED)

class JobStatusView(APIView):
    def get(self, request, job_id):
        try:
            job = ReconciliationJob.objects.get(id=job_id)
            return Response(ReconciliationJobSerializer(job).data)
        except ReconciliationJob.DoesNotExist:
            return Response({"error": "Job not found"}, status=status.HTTP_404_NOT_FOUND)


class DashboardView(TemplateView):
    template_name = "api/dashboard.html"
