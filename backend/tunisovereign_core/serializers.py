"""DRF serializers for the Track 6 domain, with explicit validation rules."""
import re

from rest_framework import serializers

from .models import (
    AgentLoopExecution,
    AnalysisMetric,
    AuditFinding,
    Cohort,
    ProjectSubmission,
    VerifiableCredentialReceipt,
)

# Allowed ranges per metric type (see docs: thresholds from the DS2 spec, Track 6).
METRIC_RANGES = {
    AnalysisMetric.MetricType.CYCLOMATIC: (1.0, 1000.0),    # cyclomatic complexity >= 1
    AnalysisMetric.MetricType.TEST_PASS: (0.0, 100.0),      # percentage
    AnalysisMetric.MetricType.SECURITY_SCORE: (0.0, 10000.0),  # number of high-severity findings
    AnalysisMetric.MetricType.AST_SIMILARITY: (0.0, 100.0),  # percentage
}

GIT_URL_RE = re.compile(r"^https?://(www\.)?(github\.com|gitlab\.com|bitbucket\.org)/[\w.\-]+/[\w.\-]+/?(\.git)?$")


class CohortSerializer(serializers.ModelSerializer):
    submissions_count = serializers.IntegerField(source="submissions.count", read_only=True)

    class Meta:
        model = Cohort
        fields = "__all__"

    def validate_min_test_pass_pct(self, value):
        if not 0 <= value <= 100:
            raise serializers.ValidationError("Must be between 0 and 100.")
        return value


class ProjectSubmissionSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source="student.username", read_only=True)

    class Meta:
        model = ProjectSubmission
        fields = "__all__"
        # `student` is set from the logged-in user for students; status is managed by staff.
        read_only_fields = ("student", "submitted_at")

    def validate_repo_url(self, value):
        if not GIT_URL_RE.match(value):
            raise serializers.ValidationError(
                "Repository URL must point to GitHub, GitLab or Bitbucket (https://github.com/user/repo)."
            )
        return value

    def validate_status(self, value):
        request = self.context.get("request")
        if request and request.user.role == "STUDENT" and value != ProjectSubmission.Status.SUBMITTED:
            raise serializers.ValidationError("Students cannot change the submission status.")
        return value


class AnalysisMetricSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="submission.project_code", read_only=True)

    class Meta:
        model = AnalysisMetric
        fields = "__all__"

    def validate(self, attrs):
        metric_type = attrs.get("metric_type", getattr(self.instance, "metric_type", None))
        value = attrs.get("value", getattr(self.instance, "value", None))
        if metric_type in METRIC_RANGES and value is not None:
            low, high = METRIC_RANGES[metric_type]
            if not low <= value <= high:
                raise serializers.ValidationError(
                    {"value": f"For {metric_type} the value must be between {low} and {high}."}
                )
        return attrs


class AuditFindingSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="submission.project_code", read_only=True)

    class Meta:
        model = AuditFinding
        fields = "__all__"
        read_only_fields = ("detected_at",)


class VerifiableCredentialReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerifiableCredentialReceipt
        fields = "__all__"


class AgentLoopExecutionSerializer(serializers.ModelSerializer):
    vc_receipt = VerifiableCredentialReceiptSerializer(read_only=True)

    class Meta:
        model = AgentLoopExecution
        fields = "__all__"
