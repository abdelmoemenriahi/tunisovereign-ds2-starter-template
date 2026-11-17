from django.test import TransactionTestCase

import grpc

from grpc_service import signing, tunisovereign_pb2 as pb2, tunisovereign_pb2_grpc as pb2_grpc
from grpc_service.server import build_server
from simulator.tunisian_simulator import generate_metrics, send_stream, send_urgent_audit
from tunisovereign_core.models import AgentLoopExecution, AnalysisMetric, AuditFinding

from .helpers import make_cohort, make_submission, make_user

CODES = ["TSK-2026-001", "TSK-2026-002", "TSK-2026-003", "TSK-2026-004"]  # healthy, weak_tests, plagiarized, insecure


class GrpcIngestionTests(TransactionTestCase):
    def setUp(self):
        cohort = make_cohort()
        student = make_user("grpcstu")
        for code in CODES:
            make_submission(cohort, student, code)
        self.server, port = build_server("127.0.0.1:0", max_workers=4)
        self.server.start()
        self.target = f"127.0.0.1:{port}"

    def tearDown(self):
        self.server.stop(0).wait()

    # ---- simulator ----
    def test_simulator_is_reproducible(self):
        a = generate_metrics(CODES, days=10, seed=7)
        b = generate_metrics(CODES, days=10, seed=7)
        c = generate_metrics(CODES, days=10, seed=8)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertGreater(sum(r["anomaly_label"] for r in a), 0)

    # ---- StreamTelemetry ----
    def test_stream_stores_metrics_over_grpc(self):
        records = generate_metrics(CODES, days=10, seed=42)
        ack = send_stream(records, self.target)
        self.assertEqual(ack.accepted_count, len(records))
        self.assertEqual(ack.rejected_count, 0)
        self.assertEqual(AnalysisMetric.objects.count(), len(records))
        self.assertTrue(AnalysisMetric.objects.filter(ingestion_protocol="gRPC").exists())

    def test_anomalies_open_findings_and_pending_agent_run(self):
        ack = send_stream(generate_metrics(CODES, days=10, seed=42), self.target)
        self.assertTrue(ack.anomaly_triggered)
        self.assertGreaterEqual(ack.findings_created, 3)
        types = set(AuditFinding.objects.values_list("finding_type", flat=True))
        self.assertIn("AST_PLAGIARISM", types)
        self.assertIn("LOW_TESTS", types)
        self.assertTrue(AgentLoopExecution.objects.filter(thread_id=ack.agent_thread_id).exists())

    def test_healthy_project_creates_no_critical_finding(self):
        healthy = [r for r in generate_metrics(CODES, days=10, seed=42) if r["profile"] == "healthy"]
        ack = send_stream(healthy, self.target)
        self.assertFalse(ack.anomaly_triggered)
        self.assertFalse(AuditFinding.objects.filter(severity="CRITICAL").exists())

    def test_bad_signature_unknown_project_and_bad_value_are_rejected(self):
        ts = "2026-11-20T10:00:00+00:00"
        good = pb2.TelemetryPacket(project_code=CODES[0], metric_type="TESTPASS", value=90.0, iso_timestamp=ts,
                                   signature_hmac=signing.sign(CODES[0], "TESTPASS", 90.0, ts))
        forged = pb2.TelemetryPacket(project_code=CODES[0], metric_type="TESTPASS", value=99.0, iso_timestamp=ts,
                                     signature_hmac="0" * 64)
        unknown = pb2.TelemetryPacket(project_code="NOPE", metric_type="TESTPASS", value=90.0, iso_timestamp=ts,
                                      signature_hmac=signing.sign("NOPE", "TESTPASS", 90.0, ts))
        out_of_range = pb2.TelemetryPacket(project_code=CODES[0], metric_type="TESTPASS", value=250.0, iso_timestamp=ts,
                                           signature_hmac=signing.sign(CODES[0], "TESTPASS", 250.0, ts))
        with grpc.insecure_channel(self.target) as ch:
            ack = pb2_grpc.TelemetryIngestServiceStub(ch).StreamTelemetry(iter([good, forged, unknown, out_of_range]))
        self.assertEqual((ack.accepted_count, ack.rejected_count), (1, 3))
        self.assertEqual(AnalysisMetric.objects.count(), 1)

    # ---- TriggerUrgentAudit ----
    def test_urgent_audit_unary_rpc(self):
        resp = send_urgent_audit(CODES[2], "Suspicious commit history", self.target)
        self.assertEqual(resp.status, "AUDIT_QUEUED")
        self.assertTrue(AuditFinding.objects.filter(submission__project_code=CODES[2], description__contains="Urgent").exists())
        self.assertTrue(AgentLoopExecution.objects.filter(thread_id=resp.agent_thread_id).exists())

    def test_urgent_audit_unknown_project_is_not_found(self):
        with self.assertRaises(grpc.RpcError) as ctx:
            send_urgent_audit("DOES-NOT-EXIST", "x", self.target)
        self.assertEqual(ctx.exception.code(), grpc.StatusCode.NOT_FOUND)
