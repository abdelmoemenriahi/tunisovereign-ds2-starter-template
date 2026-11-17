"""GraphQL tests, including the proof that the DataLoaders remove the N+1 problem."""
import asyncio
from unittest import mock

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import connections
from django.db.backends.utils import CursorWrapper
from django.test import TransactionTestCase

from tunisovereign_core.models import AgentLoopExecution, AuditFinding, VerifiableCredentialReceipt
from tunisovereign_core.schema_graphql import build_context, schema

from .helpers import Role, make_cohort, make_submission, make_user

QUERY = """
{
  cohorts {
    name
    submissions {
      projectCode
      studentUsername
      latestFindings { severity findingType }
      agentRuns { threadId vcReceipt { txHash } }
    }
  }
}
"""


def run_graphql(query, user):
    async def _run():
        try:
            return await schema.execute(query, context_value=build_context(user))
        finally:  # close the DB connection of the worker thread (clean test-DB teardown)
            await sync_to_async(connections.close_all)()

    return asyncio.run(_run())


def count_queries(func):
    """Count every SQL statement executed (any thread) while `func` runs."""
    counter = {"n": 0}
    original = CursorWrapper.execute

    def counting(self, sql, params=None):
        counter["n"] += 1
        return original(self, sql, params)

    with mock.patch.object(CursorWrapper, "execute", counting):
        result = func()
    return result, counter["n"]


def populate(n_cohorts, subs_per_cohort=3, findings_per_sub=4):
    student = make_user(f"stu{n_cohorts}")
    for c in range(n_cohorts):
        cohort = make_cohort(f"Cohort {n_cohorts}-{c}")
        for s in range(subs_per_cohort):
            sub = make_submission(cohort, student, f"P-{n_cohorts}-{c}-{s}")
            for k in range(findings_per_sub):
                AuditFinding.objects.create(submission=sub, finding_type="OTHER", severity="LOW")
            run = AgentLoopExecution.objects.create(
                thread_id=f"t-{sub.id}", submission=sub, trigger_source="test",
                final_recommendation="ok", confidence_score=0.9,
            )
            VerifiableCredentialReceipt.objects.create(
                agent_execution=run, student_did=f"did:tuni:{sub.id}", vc_commitment_hash=f"0x{sub.id:064x}",
                tx_hash=f"0x{sub.id + 10**6:064x}", block_number=sub.id,
            )


class GraphQLTests(TransactionTestCase):
    def test_nested_query_returns_full_chain(self):
        populate(1, subs_per_cohort=2)
        admin = make_user("adm", Role.NATIONAL_ADMIN)
        result = run_graphql(QUERY, admin)
        self.assertIsNone(result.errors, result.errors)
        subs = result.data["cohorts"][0]["submissions"]
        self.assertEqual(len(subs), 2)
        self.assertEqual(len(subs[0]["latestFindings"]), 4)
        self.assertTrue(subs[0]["agentRuns"][0]["vcReceipt"]["txHash"].startswith("0x"))

    def test_dataloader_prevents_n_plus_one(self):
        """Query count depends on query DEPTH, not on the number of rows."""
        populate(2)
        admin = make_user("adm", Role.NATIONAL_ADMIN)
        _, small = count_queries(lambda: run_graphql(QUERY, admin))
        populate(8)  # 4x more cohorts, 4x more submissions, 4x more findings
        result, large = count_queries(lambda: run_graphql(QUERY, admin))
        self.assertIsNone(result.errors, result.errors)
        self.assertEqual(len(result.data["cohorts"]), 10)
        self.assertEqual(small, large, f"N+1 detected: {small} queries vs {large}")
        # 1 cohorts + 1 submissions + 1 findings + 1 runs + 1 receipts
        self.assertLessEqual(large, 5)

    def test_latest_findings_limited_to_10_per_submission(self):
        populate(1, subs_per_cohort=1, findings_per_sub=15)
        result = run_graphql(QUERY, make_user("adm", Role.NATIONAL_ADMIN))
        self.assertEqual(len(result.data["cohorts"][0]["submissions"][0]["latestFindings"]), 10)

    def test_student_only_sees_own_submissions(self):
        cohort = make_cohort()
        a, b = make_user("a"), make_user("b")
        make_submission(cohort, a, "A-1")
        make_submission(cohort, b, "B-1")
        result = run_graphql("{ cohorts { submissions { projectCode } } }", a)
        codes = [s["projectCode"] for s in result.data["cohorts"][0]["submissions"]]
        self.assertEqual(codes, ["A-1"])

    def test_anonymous_is_rejected(self):
        result = run_graphql(QUERY, AnonymousUser())
        self.assertIsNotNone(result.errors)
        self.assertIn("Authentication required", result.errors[0].message)
