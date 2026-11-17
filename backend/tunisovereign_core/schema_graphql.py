"""GraphQL API (Strawberry) with DataLoader batching - Track 6 TuniSkill-DID.

One round-trip can fetch:
    Cohort -> Submissions -> latest 10 Findings -> Agent runs -> Verifiable credential receipt

WHY DataLoader?  A naive resolver would run one SQL query per parent row (the "N+1"
problem: 1 query for N cohorts + N queries for their submissions + ...).
Each DataLoader below collects all the keys requested during one event-loop tick and
runs ONE query for the whole batch, so the number of SQL queries depends on the
*depth* of the GraphQL query (5 here), never on the number of rows.

Authentication: JWT Bearer token (same as REST). A logged-in Django session is also
accepted so GraphiQL can be used in the browser after logging in at /admin/ (dev only).
Row-level security: students only see their own submissions (permissions.submissions_for).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import strawberry
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from graphql import GraphQLError
from rest_framework_simplejwt.authentication import JWTAuthentication
from strawberry.dataloader import DataLoader
from strawberry.django.views import AsyncGraphQLView
from strawberry.scalars import JSON
from strawberry.types import Info

from .models import AgentLoopExecution, AuditFinding, Cohort, VerifiableCredentialReceipt
from .permissions import submissions_for

LATEST_FINDINGS_LIMIT = 10


# ---------------------------------------------------------------------------
# DataLoaders (one batched query each) - created per request, bound to the user
# ---------------------------------------------------------------------------
def _align(keys: List[Any], grouped: Dict[Any, Any], default):
    """DataLoader contract: return results in the SAME order as `keys`."""
    return [grouped.get(k, default() if callable(default) else default) for k in keys]


@dataclass
class Loaders:
    submissions_by_cohort: DataLoader
    findings_by_submission: DataLoader
    runs_by_submission: DataLoader
    receipt_by_execution: DataLoader


def make_loaders(user) -> Loaders:
    async def load_submissions(cohort_ids: List[Any]):
        def query():
            grouped: Dict[Any, list] = {}
            qs = (
                submissions_for(user)
                .filter(cohort_id__in=cohort_ids)
                .select_related("student")  # avoids N+1 on student_username
                .order_by("-submitted_at")
            )
            for sub in qs:
                grouped.setdefault(sub.cohort_id, []).append(sub)
            return _align(cohort_ids, grouped, list)

        return await sync_to_async(query)()

    async def load_findings(submission_ids: List[Any]):
        def query():
            # Window function: keep only the latest N findings PER submission, in SQL.
            qs = (
                AuditFinding.objects.filter(submission_id__in=submission_ids)
                .annotate(
                    rn=Window(
                        expression=RowNumber(),
                        partition_by=[F("submission_id")],
                        order_by=[F("detected_at").desc(), F("id").desc()],
                    )
                )
                .filter(rn__lte=LATEST_FINDINGS_LIMIT)
                .order_by("submission_id", "-detected_at")
            )
            grouped: Dict[Any, list] = {}
            for f in qs:
                grouped.setdefault(f.submission_id, []).append(f)
            return _align(submission_ids, grouped, list)

        return await sync_to_async(query)()

    async def load_runs(submission_ids: List[Any]):
        def query():
            grouped: Dict[Any, list] = {}
            qs = AgentLoopExecution.objects.filter(submission_id__in=submission_ids).order_by("-created_at")
            for run in qs:
                grouped.setdefault(run.submission_id, []).append(run)
            return _align(submission_ids, grouped, list)

        return await sync_to_async(query)()

    async def load_receipts(execution_ids: List[Any]):
        def query():
            qs = VerifiableCredentialReceipt.objects.filter(agent_execution_id__in=execution_ids)
            grouped = {r.agent_execution_id: r for r in qs}
            return _align(execution_ids, grouped, None)

        return await sync_to_async(query)()

    return Loaders(
        submissions_by_cohort=DataLoader(load_fn=load_submissions),
        findings_by_submission=DataLoader(load_fn=load_findings),
        runs_by_submission=DataLoader(load_fn=load_runs),
        receipt_by_execution=DataLoader(load_fn=load_receipts),
    )


# ---------------------------------------------------------------------------
# Request context + authentication
# ---------------------------------------------------------------------------
@dataclass
class TuniContext:
    user: Any
    loaders: Loaders
    request: Any = None
    response: Any = None


def build_context(user, request=None, response=None) -> TuniContext:
    return TuniContext(user=user, loaders=make_loaders(user), request=request, response=response)


@sync_to_async
def _authenticate(request):
    try:
        result = JWTAuthentication().authenticate(request)
    except Exception:  # invalid / expired token -> treated as anonymous
        result = None
    if result:
        return result[0]
    user = getattr(request, "user", None)
    return user if (user is not None and user.is_authenticated) else AnonymousUser()


class TuniGraphQLView(AsyncGraphQLView):
    async def get_context(self, request, response):
        user = await _authenticate(request)
        return build_context(user, request, response)


def require_user(info):
    user = info.context.user
    if not (user and user.is_authenticated):
        raise GraphQLError("Authentication required: send 'Authorization: Bearer <access token>'.")
    return user


# ---------------------------------------------------------------------------
# GraphQL types (ORM instances are returned directly; fields read model attributes)
# ---------------------------------------------------------------------------
@strawberry.type
class VCReceiptType:
    student_did: str
    vc_commitment_hash: str
    tx_hash: str
    block_number: int
    network_name: str
    is_verified_on_chain: bool


@strawberry.type
class AgentRunType:
    thread_id: str
    trigger_source: str
    final_recommendation: str
    confidence_score: float
    oral_defense_questions: JSON
    created_at: datetime

    @strawberry.field
    async def vc_receipt(self, info: Info) -> Optional[VCReceiptType]:
        return await info.context.loaders.receipt_by_execution.load(self.id)


@strawberry.type
class FindingType:
    id: strawberry.ID
    finding_type: str
    severity: str
    description: str
    isolation_forest_score: float
    forecasted_skill_gap_pct: float
    detected_at: datetime


@strawberry.type
class SubmissionType:
    id: strawberry.ID
    project_code: str
    title: str
    repo_url: str
    primary_language: str
    status: str
    submitted_at: datetime

    @strawberry.field
    def student_username(self) -> str:
        return self.student.username  # select_related in the loader -> no extra query

    @strawberry.field
    async def latest_findings(self, info: Info) -> List[FindingType]:
        return await info.context.loaders.findings_by_submission.load(self.id)

    @strawberry.field
    async def agent_runs(self, info: Info) -> List[AgentRunType]:
        return await info.context.loaders.runs_by_submission.load(self.id)


@strawberry.type
class CohortType:
    id: strawberry.ID
    name: str
    institution: str
    governorate: str
    track_domain: str
    min_test_pass_pct: float
    max_high_severity_findings: int

    @strawberry.field
    async def submissions(self, info: Info) -> List[SubmissionType]:
        return await info.context.loaders.submissions_by_cohort.load(self.id)


@strawberry.type
class MeType:
    username: str
    role: str
    institution: str
    governorate: str


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: Info) -> MeType:
        return require_user(info)

    @strawberry.field
    async def cohorts(
        self, info: Info, institution: Optional[str] = None, governorate: Optional[str] = None
    ) -> List[CohortType]:
        require_user(info)

        def query():
            qs = Cohort.objects.all().order_by("name")
            if institution:
                qs = qs.filter(institution__iexact=institution)
            if governorate:
                qs = qs.filter(governorate__iexact=governorate)
            return list(qs)

        return await sync_to_async(query)()


schema = strawberry.Schema(query=Query)
