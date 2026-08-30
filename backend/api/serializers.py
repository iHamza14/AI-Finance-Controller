from rest_framework import serializers
from .models import ReconciliationJob, ReconciliationReport

class ReconciliationReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationReport
        fields = '__all__'

class ReconciliationJobSerializer(serializers.ModelSerializer):
    report = ReconciliationReportSerializer(read_only=True)
    class Meta:
        model = ReconciliationJob
        fields = '__all__'
