# TuniSkill-DID (Track 6) - DS2 TuniSovereign-AI

University-to-industry skills auditor with W3C Verifiable Credentials.
Stack: Django 6 - DRF + SimpleJWT - Strawberry GraphQL - gRPC (proto3) - PostgreSQL 16 - Redis.

**Status: Week 1 complete** (foundation + 3 protocols + UML). Weeks 2-4 (ML, LangGraph agent, FastMCP,
Solidity/ZK, dashboard, n8n) are not part of Week 1. The files `agent/`, `mcp_server/`, `contracts/`,
`dashboard/`, `backend/tunisovereign_core/ml_anomaly.py` are still the professor's Track 1 starter and will be adapted later.

## Setup
```powershell
copy .env.example .env                 # then edit secrets
docker compose up -d db redis          # PostgreSQL on port 55432, Redis on 6379
pipenv install                         # (re-locks: django-filter was added)
pipenv shell
cd backend
python manage.py migrate
python manage.py seed_demo             # demo users/cohort/6 projects (password Demo-Pass-2026!)
python manage.py runserver             # http://127.0.0.1:8000
```
Demo users: `student1..4`, `mentor1`, `admin1`, `agent1`.

## Run the three protocols
| Protocol | How | URL / port |
|---|---|---|
| REST | `python manage.py runserver` | `/api/v1/` (browsable API) |
| GraphQL | same server | `/graphql/` (GraphiQL; header `Authorization: Bearer <access>`) |
| gRPC | from repo root: `python -m grpc_service.server` | `localhost:50051` |
| Simulator -> gRPC | from repo root: `python -m simulator.tunisian_simulator --seed 42 --days 14` | |

If Python reports a protobuf version error: `python grpc_service/generate_stubs.py`.

### Authentication
`POST /api/auth/register/` (always creates a STUDENT) - `POST /api/auth/login/` - `POST /api/auth/refresh/` -
`GET /api/auth/me/` - `GET /api/auth/admin-only/` (403 unless NATIONAL_ADMIN).
Token claims: `role`, `institution`, `governorate`, `wallet_address`. Higher roles are assigned in `/admin/`.

### REST endpoints (`/api/v1/`, JWT required)
`cohorts/` `submissions/` `metrics/` `findings/` `executions/` `credentials/` - filters
(`?status=`, `?severity=`, `?metric_type=&min_value=`, `?cohort=`), `?search=`, `?ordering=`, pagination.

## Tests (33)
```powershell
cd backend
python manage.py test tunisovereign_core
```
Covers JWT/RBAC, REST rules and validation, GraphQL (including the N+1 proof: the query count stays
constant when the data grows 4x), gRPC streaming, HMAC rejection and the reproducible simulator.

## UML
`docs/uml_class_diagram.md` (class diagram generated from `models.py` with `docs/generate_uml.py`, plus 4 sequence diagrams).
Details, rubric mapping and oral-defense notes: `docs/WEEK1_REPORT.md`.
