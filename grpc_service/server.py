"""gRPC ingestion server (proto3 + grpcio) - Track 6 TuniSkill-DID.

Run from the repository root (PostgreSQL must be up and migrated):
    python -m grpc_service.server

StreamTelemetry   (client-streaming) -> verifies HMAC, stores AnalysisMetric rows,
                                         opens AuditFinding rows via threshold rules.
TriggerUrgentAudit (unary)           -> opens a MEDIUM finding + a pending agent run.
"""
import os
import sys
import time
import uuid
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

import grpc

ROOT = Path(__file__).resolve().parent.parent


def bootstrap_django():
    """Make the Django ORM usable when this file is run as a standalone process."""
    import django
    from django.apps import apps

    if apps.ready:
        return
    for p in (ROOT, ROOT / "backend"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


bootstrap_django()

from django.db import close_old_connections, connections  # noqa: E402
from django.utils.dateparse import parse_datetime  # noqa: E402

from grpc_service import signing, tunisovereign_pb2 as pb2, tunisovereign_pb2_grpc as pb2_grpc  # noqa: E402
from tunisovereign_core.models import (  # noqa: E402
    AgentLoopExecution,
    AnalysisMetric,
    AuditFinding,
    ProjectSubmission,
)
from tunisovereign_core.rules import evaluate_metric  # noqa: E402
from tunisovereign_core.serializers import METRIC_RANGES  # noqa: E402

VALID_METRIC_TYPES = {choice[0] for choice in AnalysisMetric.MetricType.choices}
BATCH_SIZE = 200


def _open_pending_agent_run(submission, trigger_source: str, reason: str) -> str:
    """Create a placeholder agent execution. The real LangGraph loop is wired in Week 3."""
    thread_id = f"audit-{submission.project_code}-{uuid.uuid4().hex[:8]}"
    AgentLoopExecution.objects.create(
        thread_id=thread_id,
        submission=submission,
        trigger_source=trigger_source,
        input_transcript=reason,
        final_recommendation="PENDING: agent loop not connected yet (Week 3).",
        confidence_score=0.0,
    )
    return thread_id


class TelemetryIngestServicer(pb2_grpc.TelemetryIngestServiceServicer):
    def StreamTelemetry(self, request_iterator, context):
        accepted = rejected = findings_created = 0
        thread_id = ""
        anomaly = False
        submissions = {}       # cache: project_code -> ProjectSubmission | None
        opened = set()         # (submission_id, finding_type): one finding per type per stream
        buffer = []

        def flush():
            if buffer:
                AnalysisMetric.objects.bulk_create(buffer)
                buffer.clear()

        try:
            for packet in request_iterator:
                code = packet.project_code
                if code not in submissions:
                    submissions[code] = (
                        ProjectSubmission.objects.select_related("cohort").filter(project_code=code).first()
                    )
                sub = submissions[code]
                ts = parse_datetime(packet.iso_timestamp) if packet.iso_timestamp else None
                valid = (
                    sub is not None
                    and ts is not None
                    and packet.metric_type in VALID_METRIC_TYPES
                    and METRIC_RANGES[packet.metric_type][0] <= packet.value <= METRIC_RANGES[packet.metric_type][1]
                    and signing.verify(
                        code, packet.metric_type, packet.value, packet.iso_timestamp, packet.signature_hmac
                    )
                )
                if not valid:
                    rejected += 1
                    continue

                buffer.append(
                    AnalysisMetric(
                        submission=sub,
                        timestamp=ts,
                        metric_type=packet.metric_type,
                        value=packet.value,
                        ingestion_protocol="gRPC",
                    )
                )
                accepted += 1
                if len(buffer) >= BATCH_SIZE:
                    flush()

                spec = evaluate_metric(sub.cohort, packet.metric_type, packet.value)
                if spec and (sub.id, spec.finding_type) not in opened:
                    opened.add((sub.id, spec.finding_type))
                    AuditFinding.objects.create(
                        submission=sub,
                        finding_type=spec.finding_type,
                        severity=spec.severity,
                        description=spec.description,
                    )
                    findings_created += 1
                    if spec.severity == AuditFinding.Severity.CRITICAL and not anomaly:
                        anomaly = True
                        thread_id = _open_pending_agent_run(sub, "gRPC_Anomaly", spec.description)
            flush()
        finally:
            close_old_connections()

        return pb2.IngestAck(
            accepted_count=accepted,
            rejected_count=rejected,
            findings_created=findings_created,
            anomaly_triggered=anomaly,
            agent_thread_id=thread_id,
        )

    def TriggerUrgentAudit(self, request, context):
        try:
            sub = ProjectSubmission.objects.filter(project_code=request.project_code).first()
            if sub is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Unknown project_code '{request.project_code}'.")
                return pb2.AuditResponse(status="PROJECT_NOT_FOUND")
            reason = request.reason or "Urgent audit requested over gRPC."
            AuditFinding.objects.create(
                submission=sub,
                finding_type=AuditFinding.FindingType.OTHER,
                severity=AuditFinding.Severity.MEDIUM,
                description=f"Urgent audit: {reason}",
            )
            thread_id = _open_pending_agent_run(sub, "gRPC_Urgent_Audit", reason)
            return pb2.AuditResponse(status="AUDIT_QUEUED", tx_hash="", agent_thread_id=thread_id)
        finally:
            close_old_connections()


def build_server(address: str = "[::]:50051", max_workers: int = 8):
    """Create (not start) the server. Returns (server, bound_port); port 0 = pick a free one."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    pb2_grpc.add_TelemetryIngestServiceServicer_to_server(TelemetryIngestServicer(), server)
    port = server.add_insecure_port(address)
    return server, port


def serve(port: int = 50051):
    server, bound = build_server(f"[::]:{port}")
    server.start()
    print(f"[TuniSkill-DID gRPC] listening on port {bound} (proto3, HTTP/2)")
    return server


if __name__ == "__main__":
    srv = serve(int(os.getenv("GRPC_PORT", "50051")))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.stop(0)
