"""django-filter FilterSets: query-string filtering for the REST list endpoints."""
import django_filters as df

from .models import AnalysisMetric, AuditFinding, ProjectSubmission


class ProjectSubmissionFilter(df.FilterSet):
    submitted_after = df.DateTimeFilter(field_name="submitted_at", lookup_expr="gte")
    submitted_before = df.DateTimeFilter(field_name="submitted_at", lookup_expr="lte")

    class Meta:
        model = ProjectSubmission
        fields = ["cohort", "student", "status", "primary_language"]


class AnalysisMetricFilter(df.FilterSet):
    min_value = df.NumberFilter(field_name="value", lookup_expr="gte")
    max_value = df.NumberFilter(field_name="value", lookup_expr="lte")
    after = df.DateTimeFilter(field_name="timestamp", lookup_expr="gte")
    before = df.DateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AnalysisMetric
        fields = ["submission", "metric_type", "ingestion_protocol"]


class AuditFindingFilter(df.FilterSet):
    detected_after = df.DateTimeFilter(field_name="detected_at", lookup_expr="gte")

    class Meta:
        model = AuditFinding
        fields = ["submission", "severity", "finding_type"]
