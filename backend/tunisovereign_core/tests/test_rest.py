from django.test import TestCase
from rest_framework.test import APIClient

from tunisovereign_core.models import AnalysisMetric, AuditFinding

from .helpers import Role, make_cohort, make_submission, make_user


class RestApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cohort = make_cohort()
        cls.s1, cls.s2 = make_user("s1"), make_user("s2")
        cls.mentor = make_user("mentor", Role.MENTOR_AUDITOR)
        cls.admin = make_user("admin", Role.NATIONAL_ADMIN)
        cls.agent = make_user("agent", Role.AGENT_SERVICE)
        cls.sub1 = make_submission(cls.cohort, cls.s1, "P-001")
        cls.sub2 = make_submission(cls.cohort, cls.s2, "P-002")

    def as_user(self, user):
        c = APIClient()
        if user:
            c.force_authenticate(user)
        return c

    # ---- authentication / status codes ----
    def test_anonymous_gets_401(self):
        self.assertEqual(self.as_user(None).get("/api/v1/submissions/").status_code, 401)

    def test_unknown_object_is_404(self):
        self.assertEqual(self.as_user(self.admin).get("/api/v1/submissions/99999/").status_code, 404)

    # ---- submissions ----
    def test_student_creates_submission_and_is_set_as_owner(self):
        resp = self.as_user(self.s1).post(
            "/api/v1/submissions/",
            {"cohort": str(self.cohort.id), "project_code": "P-NEW", "title": "New",
             "repo_url": "https://github.com/s1/new"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["student"], self.s1.id)
        self.assertEqual(resp.data["status"], "SUBMITTED")

    def test_invalid_repo_url_is_400(self):
        resp = self.as_user(self.s1).post(
            "/api/v1/submissions/",
            {"cohort": str(self.cohort.id), "project_code": "P-BAD", "title": "Bad", "repo_url": "https://evil.example/x"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("repo_url", resp.data)

    def test_student_cannot_self_assign_a_status(self):
        resp = self.as_user(self.s1).post(
            "/api/v1/submissions/",
            {"cohort": str(self.cohort.id), "project_code": "P-CHEAT", "title": "x",
             "repo_url": "https://github.com/s1/x", "status": "CREDENTIAL_ISSUED"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_student_sees_only_own_submissions_staff_sees_all(self):
        self.assertEqual(self.as_user(self.s1).get("/api/v1/submissions/").data["count"], 1)
        self.assertEqual(self.as_user(self.mentor).get("/api/v1/submissions/").data["count"], 2)
        self.assertEqual(self.as_user(self.s1).get(f"/api/v1/submissions/{self.sub2.id}/").status_code, 404)

    def test_mentor_cannot_create_submission_but_can_update_status(self):
        self.assertEqual(self.as_user(self.mentor).post("/api/v1/submissions/", {}, format="json").status_code, 403)
        resp = self.as_user(self.mentor).patch(
            f"/api/v1/submissions/{self.sub1.id}/", {"status": "AUDITED"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "AUDITED")
        self.assertEqual(self.as_user(self.s1).patch(f"/api/v1/submissions/{self.sub1.id}/", {"status": "AUDITED"}, format="json").status_code, 403)

    def test_submission_filters_and_search(self):
        self.sub2.status = "AUDITED"
        self.sub2.save()
        c = self.as_user(self.mentor)
        self.assertEqual(c.get("/api/v1/submissions/?status=AUDITED").data["count"], 1)
        self.assertEqual(c.get(f"/api/v1/submissions/?cohort={self.cohort.id}").data["count"], 2)
        self.assertEqual(c.get("/api/v1/submissions/?search=P-001").data["count"], 1)

    # ---- metrics ----
    def metric_payload(self, **kw):
        base = {"submission": self.sub1.id, "timestamp": "2026-11-20T10:00:00Z", "metric_type": "TESTPASS", "value": 90}
        base.update(kw)
        return base

    def test_student_cannot_write_metrics_agent_can(self):
        self.assertEqual(self.as_user(self.s1).post("/api/v1/metrics/", self.metric_payload(), format="json").status_code, 403)
        resp = self.as_user(self.agent).post("/api/v1/metrics/", self.metric_payload(), format="json")
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_metric_value_validated_per_type(self):
        c = self.as_user(self.agent)
        self.assertEqual(c.post("/api/v1/metrics/", self.metric_payload(value=140), format="json").status_code, 400)
        self.assertEqual(c.post("/api/v1/metrics/", self.metric_payload(metric_type="CYCLO", value=0), format="json").status_code, 400)

    def test_metrics_scoped_and_filterable(self):
        for sub, v in ((self.sub1, 80), (self.sub1, 95), (self.sub2, 60)):
            AnalysisMetric.objects.create(submission=sub, timestamp="2026-11-20T10:00:00Z", metric_type="TESTPASS", value=v)
        self.assertEqual(self.as_user(self.s1).get("/api/v1/metrics/").data["count"], 2)
        self.assertEqual(self.as_user(self.mentor).get("/api/v1/metrics/").data["count"], 3)
        self.assertEqual(self.as_user(self.mentor).get("/api/v1/metrics/?min_value=90").data["count"], 1)
        self.assertEqual(self.as_user(self.mentor).get(f"/api/v1/metrics/?submission={self.sub2.id}").data["count"], 1)

    # ---- findings / cohorts / credentials ----
    def test_findings_visibility_and_write_permission(self):
        AuditFinding.objects.create(submission=self.sub2, finding_type="AST_PLAGIARISM", severity="CRITICAL")
        self.assertEqual(self.as_user(self.s1).get("/api/v1/findings/").data["count"], 0)
        self.assertEqual(self.as_user(self.mentor).get("/api/v1/findings/?severity=CRITICAL").data["count"], 1)
        resp = self.as_user(self.s1).post("/api/v1/findings/", {"submission": self.sub1.id, "finding_type": "OTHER", "severity": "LOW"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_cohort_write_is_admin_only(self):
        body = {"name": "New cohort", "institution": "ISG Tunis", "governorate": "Tunis"}
        self.assertEqual(self.as_user(self.mentor).post("/api/v1/cohorts/", body, format="json").status_code, 403)
        self.assertEqual(self.as_user(self.admin).post("/api/v1/cohorts/", body, format="json").status_code, 201)
        self.assertEqual(self.as_user(self.s1).get("/api/v1/cohorts/").status_code, 200)

    def test_credentials_and_executions_are_read_only(self):
        c = self.as_user(self.admin)
        self.assertEqual(c.get("/api/v1/credentials/").status_code, 200)
        self.assertEqual(c.post("/api/v1/credentials/", {}, format="json").status_code, 405)
        self.assertEqual(c.get("/api/v1/executions/").status_code, 200)
