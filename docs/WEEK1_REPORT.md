# Week 1 report - TuniSkill-DID (Track 6)

## 1. Rubric mapping (6 pts)
| Criterion | Pts | Where |
|---|---|---|
| 1.1 REST: ViewSets, serializers, filtering, validation, status codes | 1.00 | `api_rest.py`, `serializers.py`, `filters.py`, tests `test_rest.py` |
| 1.2 GraphQL + DataLoader N+1 prevention | 1.25 | `schema_graphql.py`, test `test_dataloader_prevents_n_plus_one` |
| 1.3 gRPC + .proto + simulator ingestion | 1.25 | `protos/tunisovereign.proto`, `grpc_service/server.py`, `simulator/tunisian_simulator.py`, `test_grpc.py` |
| 2.1 Models, TextChoices, Meta indexes, UML fidelity | 1.25 | `models.py`, `docs/generate_uml.py`, `docs/uml_class_diagram.md` |
| 2.2 JWT, 4-role RBAC, `.env` secrets | 1.25 | `auth_*.py`, `permissions.py`, `settings.py` (reads `.env`), `test_auth.py` |

## 2. Design decisions (be ready to explain each)
- **Roles**: STUDENT, MENTOR_AUDITOR, NATIONAL_ADMIN (superset of mentor), AGENT_SERVICE. Public signup can only create STUDENT, so nobody can self-assign admin (`RegisterSerializer`).
- **Row-level security**: `permissions.submissions_for(user)` is used by REST *and* GraphQL: students see only their own data.
- **DataLoader**: one batched `WHERE ... IN (...)` query per GraphQL level, created per request. Query count = 5 whatever the number of rows. The latest 10 findings per submission use a SQL window function (`RowNumber`).
- **gRPC**: client-streaming `StreamTelemetry` (many packets, one ack) + unary `TriggerUrgentAudit`. Each packet is signed with HMAC-SHA256 (`GRPC_HMAC_SECRET`); forged, unknown-project or out-of-range packets are rejected and counted.
- **Thresholds** (`rules.py`): tests < cohort minimum (85 %), high-severity findings > 0, AST similarity >= 85 %, cyclomatic > 15. These are deterministic rules; Week 2 adds IsolationForest.
- **Simulator**: seeded (`--seed`), so anomaly injection is reproducible; it keeps `anomaly_label` ground truth for the Week 2 Precision/Recall/F1 evaluation.
- **Pending agent run**: a CRITICAL anomaly creates an `AgentLoopExecution` with a thread id and a "PENDING" recommendation, so Week 3 (LangGraph) can pick it up.

## 3. Probable oral questions
1. Why three protocols? REST = CRUD for clients, GraphQL = one round-trip for nested graphs, gRPC = fast binary streaming from machines.
2. What is N+1 and how do you prove it is gone? See the test: same query count with 2 and 10 cohorts.
3. Why is `role` not in the register serializer? Privilege escalation.
4. Why HMAC on gRPC packets? Only trusted sandboxes may write metrics.
5. Change a threshold live: `rules.py` (`AST_PLAGIARISM_THRESHOLD_PCT`) or `Cohort.min_test_pass_pct`.
6. What does JWT carry and how does refresh work? Claims in `TuniTokenObtainPairSerializer`; refresh via `TokenRefreshView`.

## 4. Known limitations (honest list)
- Automated tests were run on SQLite; also verified end-to-end by hand (real server + gRPC process). Run the test suite once on your PostgreSQL.
- gRPC channel is insecure (no TLS): fine for local development.
- GraphQL accepts a Django session (for GraphiQL in the browser) and is CSRF-exempt: dev convenience, use JWT only in production.
- `SECURITY` metric = number of high-severity Bandit/Semgrep findings (the model help text says "score").
- Mermaid diagrams were generated but not rendered here: export PNG/SVG from https://mermaid.live for the slides.
- Starter files for Weeks 2-4 are still Track 1 and untouched.
