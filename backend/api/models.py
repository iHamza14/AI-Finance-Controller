from django.db import models
import uuid

class ReconciliationJob(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Job {self.id} - {self.status}"

class ReconciliationReport(models.Model):
    job = models.OneToOneField(ReconciliationJob, on_delete=models.CASCADE, related_name="report")
    batch_size = models.IntegerField(default=0)
    match_rate = models.FloatField(default=0.0)
    exception_rate = models.FloatField(default=0.0)
    ml_metrics = models.JSONField(default=dict)
    exceptions = models.JSONField(default=list)

    def __str__(self):
        return f"Report for Job {self.job.id}"
