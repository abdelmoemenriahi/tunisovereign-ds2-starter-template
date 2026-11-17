from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from tunisovereign_core.api_rest import (
    AgentLoopExecutionViewSet,
    AnalysisMetricViewSet,
    AuditFindingViewSet,
    CohortViewSet,
    ProjectSubmissionViewSet,
    VerifiableCredentialViewSet,
)
from tunisovereign_core.auth_views import AdminOnlyView, LoginView, MeView, RegisterView
from tunisovereign_core.schema_graphql import TuniGraphQLView, schema

router = DefaultRouter()
router.register(r"cohorts", CohortViewSet, basename="cohort")
router.register(r"submissions", ProjectSubmissionViewSet, basename="submission")
router.register(r"metrics", AnalysisMetricViewSet, basename="metric")
router.register(r"findings", AuditFindingViewSet, basename="finding")
router.register(r"executions", AgentLoopExecutionViewSet, basename="execution")
router.register(r"credentials", VerifiableCredentialViewSet, basename="credential")

urlpatterns = [
    path("admin/", admin.site.urls),
    # --- JWT authentication ---
    path("api/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/auth/admin-only/", AdminOnlyView.as_view(), name="auth-admin-only"),
    # --- REST API ---
    path("api/v1/", include(router.urls)),
    # --- GraphQL (Strawberry + DataLoader) ---
    path("graphql/", csrf_exempt(TuniGraphQLView.as_view(schema=schema)), name="graphql"),
]
