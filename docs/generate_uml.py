"""Generate the UML class diagram (Mermaid) DIRECTLY from the Django models.

Because the diagram is produced by introspecting models.py, it cannot drift from the code
(rubric 2.1 "exact correspondence with UML"). Re-run after ANY change to models.py:

    cd backend && python ../docs/generate_uml.py      ->  docs/uml_class_diagram.md
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db import models  # noqa: E402

APP = "tunisovereign_core"
INHERITED_USER_FIELDS = {"password", "last_login", "is_superuser", "first_name", "last_name",
                         "email", "is_staff", "is_active", "date_joined", "groups", "user_permissions", "username"}


def ftype(f):
    t = f.get_internal_type().replace("Field", "")
    return {"Char": "str", "Text": "text", "Float": "float", "Boolean": "bool", "DateTime": "datetime",
            "UUID": "uuid", "PositiveInteger": "uint", "JSON": "json", "URL": "url"}.get(t, t.lower())


def build():
    out = ["classDiagram", "    direction LR"]
    rels = []
    for m in apps.get_app_config(APP).get_models():
        name = m.__name__
        out.append(f"    class {name} {{")
        if m is apps.get_model(APP, "StakeholderUser"):
            out.append("        <<AbstractUser>>")
            out.append("        +username : str (inherited)")
        for f in m._meta.get_fields():
            if not getattr(f, "concrete", False) or f.name in INHERITED_USER_FIELDS or f.name == "id" and not f.primary_key:
                continue
            if isinstance(f, models.ForeignKey) or isinstance(f, models.OneToOneField):
                kind = "1" if isinstance(f, models.OneToOneField) else "*"
                target = f.related_model.__name__
                one = '"0..1"' if f.null else '"1"'
                rels.append(f'    {target} {one} <-- "{kind}" {name} : {f.name}')
                continue
            if f.name == "id" and f.primary_key and not isinstance(f, models.UUIDField):
                continue
            mark = "#" if f.choices else "+"
            tag = " [choices]" if f.choices else ""
            idx = " [indexed]" if f.db_index and not f.primary_key else ""
            out.append(f"        {mark}{f.name} : {ftype(f)}{tag}{idx}")
        out.append("    }")
        # enums (TextChoices) declared on the model
        for attr in vars(m).values():
            if isinstance(attr, type) and issubclass(attr, models.TextChoices):
                vals = ", ".join(v for v, _ in attr.choices)
                out.append(f"    class {name}_{attr.__name__} {{")
                out.append("        <<enumeration>>")
                for v, _ in attr.choices:
                    out.append(f"        {v}")
                out.append("    }")
                rels.append(f"    {name} ..> {name}_{attr.__name__} : uses")
    out.extend(rels)
    return "\n".join(out)


SEQUENCES = {
"1. JWT authentication and role-based access (RBAC)": """sequenceDiagram
    actor U as User (Student / Mentor / Admin)
    participant API as Django REST (SimpleJWT)
    participant DB as PostgreSQL
    U->>API: POST /api/auth/register/ {username, password}
    API->>DB: INSERT StakeholderUser(role=STUDENT)
    API-->>U: 201 Created (no password in response)
    U->>API: POST /api/auth/login/
    API->>DB: SELECT user, check password
    API-->>U: 200 {access, refresh} (claims: role, institution, governorate, wallet_address)
    U->>API: GET /api/v1/... + Authorization: Bearer access
    API->>API: JWTAuthentication, then HasRole permission check
    alt role allowed
        API-->>U: 200 OK (rows scoped by role)
    else role not allowed
        API-->>U: 403 Forbidden
    end
    U->>API: POST /api/auth/refresh/ {refresh}
    API-->>U: 200 {new access}""",
"2. Student submits a project, mentor reviews it (REST)": """sequenceDiagram
    actor S as Student
    actor M as Mentor / Auditor
    participant API as REST /api/v1/
    participant DB as PostgreSQL
    S->>API: POST /submissions/ {project_code, title, repo_url}
    API->>API: validate repo_url (GitHub/GitLab/Bitbucket), reject self-set status
    API->>DB: INSERT ProjectSubmission(student=S, status=SUBMITTED)
    API-->>S: 201 Created
    M->>API: GET /findings/?severity=CRITICAL
    API->>DB: SELECT AuditFinding (all rows: staff role)
    API-->>M: 200 paginated list
    M->>API: PATCH /submissions/{id}/ {status: AUDITED}
    API-->>M: 200 OK
    S->>API: PATCH /submissions/{id}/ {status: AUDITED}
    API-->>S: 403 Forbidden (students cannot change status)""",
"3. Telemetry ingestion over gRPC and anomaly detection": """sequenceDiagram
    participant SIM as Simulator / CI sandbox (gRPC client)
    participant GRPC as gRPC server (TelemetryIngestService)
    participant RULES as Threshold rules (rules.py)
    participant DB as PostgreSQL
    SIM->>GRPC: StreamTelemetry(stream TelemetryPacket + HMAC signature)
    loop for each packet
        GRPC->>GRPC: verify HMAC, project exists, value in range
        GRPC->>DB: bulk INSERT AnalysisMetric (protocol = gRPC)
        GRPC->>RULES: evaluate_metric(cohort, type, value)
        opt threshold breached
            RULES-->>GRPC: FindingSpec (type, severity)
            GRPC->>DB: INSERT AuditFinding
            opt severity = CRITICAL
                GRPC->>DB: INSERT AgentLoopExecution (pending, Week 3 agent)
            end
        end
    end
    GRPC-->>SIM: IngestAck {accepted, rejected, findings_created, anomaly_triggered, agent_thread_id}
    SIM->>GRPC: TriggerUrgentAudit {project_code, reason}
    GRPC->>DB: INSERT AuditFinding(MEDIUM) + pending AgentLoopExecution
    GRPC-->>SIM: AuditResponse {AUDIT_QUEUED, agent_thread_id}""",
"4. GraphQL nested query with DataLoader batching (no N+1)": """sequenceDiagram
    actor C as Client (employer / dashboard)
    participant GQL as /graphql/ (Strawberry, async)
    participant DL as DataLoaders (one per request)
    participant DB as PostgreSQL
    C->>GQL: { cohorts { submissions { latestFindings agentRuns { vcReceipt } } } }
    GQL->>GQL: authenticate JWT, build context + loaders
    GQL->>DB: Q1 SELECT cohorts
    par one batched query per level
        GQL->>DL: submissions.load(cohort_id) x N
        DL->>DB: Q2 SELECT submissions WHERE cohort_id IN (...)
    end
    par
        GQL->>DL: findings.load(submission_id) x M
        DL->>DB: Q3 SELECT latest 10 findings per submission (window function)
        GQL->>DL: runs.load(submission_id) x M
        DL->>DB: Q4 SELECT agent runs WHERE submission_id IN (...)
    end
    GQL->>DL: receipt.load(execution_id) x K
    DL->>DB: Q5 SELECT receipts WHERE agent_execution_id IN (...)
    GQL-->>C: 200 JSON (always 5 queries, whatever N, M, K)""",
}

if __name__ == "__main__":
    doc = ["# UML diagrams - TuniSkill-DID (Track 6) - Week 1", "",
           "Open in GitHub, VS Code (Markdown Preview Mermaid Support) or paste each block into https://mermaid.live "
           "to export PNG/SVG for the slides.", "",
           "## UML Class Diagram (generated from `models.py`)", "",
           "> Generated by `docs/generate_uml.py` - do not edit by hand; re-run after any model change.", "",
           "```mermaid", build(), "```", "", "## UML Sequence Diagrams", ""]
    for title, body in SEQUENCES.items():
        doc += [f"### {title}", "", "```mermaid", body, "```", ""]
    (ROOT / "docs" / "uml_class_diagram.md").write_text("\n".join(doc), encoding="utf-8")
    print("Written docs/uml_class_diagram.md")
