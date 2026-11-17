"""REST API (Django REST Framework) for Track 6 - TuniSkill-DID.

Endpoints (all under /api/v1/, JWT Bearer token required):
    cohorts/        CRUD (read: any user, write: NATIONAL_ADMIN)
    submissions/    students create + see their own; staff see all and manage status
    metrics/        code-analysis metrics (read: scoped, write: mentor/admin/agent)
    findings/       audit findings    (read: scoped, write: mentor/admin/agent)
    executions/     AI agent runs     (read-only, scoped)
    credentials/    verifiable credential receipts (read-only, scoped)
"""
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .filters import AnalysisMetricFilter, AuditFindingFilter, ProjectSubmissionFilter
from .models import (
    AgentLoopExecution,
    AnalysisMetric,
    AuditFinding,
    Cohort,
    ProjectSubmission,
    VerifiableCredentialReceipt,
)
from .permissions import (
    IsMentorAuditor,
    IsStaffRole,
    IsStudent,
    ReadOnlyOrNationalAdmin,
    is_staff_role,
    submissions_for,
)
from .serializers import (
    AgentLoopExecutionSerializer,
    AnalysisMetricSerializer,
    AuditFindingSerializer,
    CohortSerializer,
    ProjectSubmissionSerializer,
    VerifiableCredentialReceiptSerializer,
)

FILTERS = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]


class StudentScopedMixin:
    """Row-level security: students only see rows linked to their own submissions."""

    student_lookup = "submission__student"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if is_staff_role(user):
            return qs
        if user.is_authenticated:
            return qs.filter(**{self.student_lookup: user})
        return qs.none()


class CohortViewSet(viewsets.ModelViewSet):
    queryset = Cohort.objects.all().order_by("-created_at")
    serializer_class = CohortSerializer
    permission_classes = [ReadOnlyOrNationalAdmin]
    filter_backends = FILTERS
    filterset_fields = ["institution", "governorate", "track_domain"]
    search_fields = ["name", "institution"]
    ordering_fields = ["name", "created_at"]


class ProjectSubmissionViewSet(viewsets.ModelViewSet):
    queryset = ProjectSubmission.objects.select_related("cohort", "student").order_by("-submitted_at")
    serializer_class = ProjectSubmissionSerializer
    filter_backends = FILTERS
    filterset_class = ProjectSubmissionFilter
    search_fields = ["project_code", "title", "student__username"]
    ordering_fields = ["submitted_at", "status", "project_code"]

    def get_permissions(self):
        if self.action == "create":
            return [IsStudent()]
        if self.action in ("update", "partial_update", "destroy"):
            return [IsMentorAuditor()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return submissions_for(self.request.user).select_related("cohort", "student").order_by("-submitted_at")

    def perform_create(self, serializer):
        serializer.save(student=self.request.user)


class AnalysisMetricViewSet(StudentScopedMixin, viewsets.ModelViewSet):
    queryset = AnalysisMetric.objects.select_related("submission").order_by("-timestamp")
    serializer_class = AnalysisMetricSerializer
    filter_backends = FILTERS
    filterset_class = AnalysisMetricFilter
    ordering_fields = ["timestamp", "value"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsStaffRole()]


class AuditFindingViewSet(StudentScopedMixin, viewsets.ModelViewSet):
    queryset = AuditFinding.objects.select_related("submission").order_by("-detected_at")
    serializer_class = AuditFindingSerializer
    filter_backends = FILTERS
    filterset_class = AuditFindingFilter
    search_fields = ["description"]
    ordering_fields = ["detected_at", "severity"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsStaffRole()]


class AgentLoopExecutionViewSet(StudentScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = (
        AgentLoopExecution.objects.select_related("submission", "vc_receipt").order_by("-created_at")
    )
    serializer_class = AgentLoopExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = FILTERS
    filterset_fields = ["submission", "trigger_source", "thread_id"]


class VerifiableCredentialViewSet(StudentScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = VerifiableCredentialReceipt.objects.select_related("agent_execution").order_by("-block_number")
    serializer_class = VerifiableCredentialReceiptSerializer
    permission_classes = [IsAuthenticated]
    student_lookup = "agent_execution__submission__student"
    filter_backends = FILTERS
    filterset_fields = ["student_did", "network_name", "is_verified_on_chain"]
