import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class StakeholderUser(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student submitting a project"
        MENTOR_AUDITOR = "MENTOR_AUDITOR", "Teacher / Industry Mentor Auditor"
        NATIONAL_ADMIN = "NATIONAL_ADMIN", "University / Ministry Admin"
        AGENT_SERVICE = "AGENT_SERVICE", "Autonomous AI Agent & MCP Service Account"

    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STUDENT)
    institution = models.CharField(max_length=120, db_index=True, default="ISG Tunis")
    governorate = models.CharField(max_length=64, db_index=True, default="Tunis")
    wallet_address = models.CharField(max_length=42, blank=True, null=True)
    preferred_dialect = models.CharField(max_length=16, default="ar-TN")


class Cohort(models.Model):
    """Promotion / department that groups student submissions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    institution = models.CharField(max_length=120, db_index=True)
    governorate = models.CharField(max_length=64, db_index=True)
    track_domain = models.CharField(max_length=64, default="Track_06_Skills_DID")
    min_test_pass_pct = models.FloatField(default=85.0, help_text="Minimum test pass rate (%)")
    max_high_severity_findings = models.PositiveIntegerField(default=0)
    contract_address = models.CharField(max_length=42, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ProjectSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ANALYZING = "ANALYZING", "Under analysis"
        AUDITED = "AUDITED", "Audited"
        DEFENSE_PENDING = "DEFENSE_PENDING", "Oral defense pending"
        CREDENTIAL_ISSUED = "CREDENTIAL_ISSUED", "Credential issued"
        REJECTED = "REJECTED", "Rejected"

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(StakeholderUser, on_delete=models.CASCADE, related_name="submissions")
    project_code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=160)
    repo_url = models.URLField()
    primary_language = models.CharField(max_length=32, default="Python")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["cohort", "status"])]

    def __str__(self):
        return self.project_code


class AnalysisMetric(models.Model):
    class MetricType(models.TextChoices):
        CYCLOMATIC = "CYCLO", "Cyclomatic Complexity"
        TEST_PASS = "TESTPASS", "Test Pass Rate (%)"
        SECURITY_SCORE = "SECURITY", "Bandit / Semgrep Security Score"
        AST_SIMILARITY = "ASTSIM", "AST Similarity Score (%)"

    submission = models.ForeignKey(ProjectSubmission, on_delete=models.CASCADE, related_name="metrics")
    timestamp = models.DateTimeField(db_index=True)
    metric_type = models.CharField(max_length=16, choices=MetricType.choices)
    value = models.FloatField()
    ingestion_protocol = models.CharField(max_length=16, default="gRPC")  # REST, gRPC, GraphQL

    class Meta:
        indexes = [models.Index(fields=["submission", "metric_type", "-timestamp"])]


class AuditFinding(models.Model):
    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        CRITICAL = "CRITICAL", "Critical (plagiarism / vulnerability / secret)"

    class FindingType(models.TextChoices):
        AST_PLAGIARISM = "AST_PLAGIARISM", "Plagiarized AST signature"
        SQL_INJECTION = "SQL_INJECTION", "Vulnerable SQL pattern"
        SECRET_EXPOSED = "SECRET_EXPOSED", "Hard-coded secret"
        LOW_TEST_COVERAGE = "LOW_TESTS", "Test pass rate below threshold"
        OTHER = "OTHER", "Other"

    submission = models.ForeignKey(ProjectSubmission, on_delete=models.CASCADE, related_name="findings")
    detected_at = models.DateTimeField(auto_now_add=True)
    finding_type = models.CharField(max_length=24, choices=FindingType.choices)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    description = models.TextField(blank=True)
    isolation_forest_score = models.FloatField(default=0.0)
    forecasted_skill_gap_pct = models.FloatField(default=0.0)

    class Meta:
        indexes = [models.Index(fields=["submission", "-detected_at"])]


class AgentLoopExecution(models.Model):
    thread_id = models.CharField(max_length=64, db_index=True)
    submission = models.ForeignKey(
        ProjectSubmission, null=True, blank=True, on_delete=models.SET_NULL, related_name="agent_runs"
    )
    trigger_source = models.CharField(max_length=64)  # Submission, gRPC_Anomaly, Scheduled_Audit
    input_transcript = models.TextField(blank=True)
    parsed_intent_json = models.JSONField(default=dict)
    mcp_tools_invoked = models.JSONField(default=list)
    skills_executed = models.JSONField(default=list)
    oral_defense_questions = models.JSONField(default=list)
    final_recommendation = models.TextField()
    confidence_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)


class VerifiableCredentialReceipt(models.Model):
    agent_execution = models.OneToOneField(
        AgentLoopExecution, on_delete=models.CASCADE, related_name="vc_receipt"
    )
    student_did = models.CharField(max_length=128)
    vc_commitment_hash = models.CharField(max_length=66, unique=True)
    public_inputs_json = models.JSONField(default=dict)
    tx_hash = models.CharField(max_length=66, unique=True)
    block_number = models.PositiveIntegerField()
    network_name = models.CharField(max_length=32, default="Foundry-Anvil-Local")
    is_verified_on_chain = models.BooleanField(default=True)