"""Code-quality telemetry simulator + gRPC client - Track 6 TuniSkill-DID.

Simulates the CI / analysis sandboxes of Tunisian university projects: every project gets
a daily analysis run over N days with realistic drift (tests improving, complexity creeping
up near deadlines) and REPRODUCIBLE injected anomalies (same --seed => same data).

Profiles (one per project, assigned round-robin):
    healthy      steady good metrics, no anomaly
    weak_tests   test pass rate collapses below the 85 % cohort minimum
    plagiarized  AST similarity jumps above the 85 % plagiarism threshold
    insecure     Bandit/Semgrep high-severity findings appear

Ground-truth labels (`anomaly_label`) are kept so Week 2 can compute Precision/Recall/F1.

Usage (repo root, gRPC server running, DB seeded with `python manage.py seed_demo`):
    python -m simulator.tunisian_simulator --seed 42 --days 14            # send via gRPC
    python -m simulator.tunisian_simulator --seed 42 --dry-run            # just print
    python -m simulator.tunisian_simulator --urgent TSK-2026-003 --reason "Suspicious commit"
"""
import argparse
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterator, List

from grpc_service import signing

DEFAULT_PROJECTS = [f"TSK-2026-{i:03d}" for i in range(1, 7)]
PROFILES = ["healthy", "weak_tests", "plagiarized", "insecure"]
ANOMALY_START_FRACTION = 0.6  # anomalies start at ~60 % of the observation window


def generate_metrics(
    projects: List[str] = None,
    days: int = 14,
    seed: int = 42,
    start: datetime = None,
) -> List[Dict]:
    """Return signed metric records. Deterministic for a given (projects, days, seed, start)."""
    projects = projects or DEFAULT_PROJECTS
    rng = random.Random(seed)
    start = start or datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    anomaly_day = int(days * ANOMALY_START_FRACTION)
    records = []

    for idx, code in enumerate(projects):
        profile = PROFILES[idx % len(PROFILES)]
        base_tests = rng.uniform(88, 96)
        base_cyclo = rng.uniform(5, 9)
        for day in range(days):
            ts = (start + timedelta(days=day, minutes=rng.randint(0, 59))).isoformat()
            progress = day / max(1, days - 1)
            anomalous = day >= anomaly_day and profile != "healthy"

            tests = min(100.0, base_tests + 4 * progress + rng.gauss(0, 1.2))
            cyclo = max(1.0, base_cyclo + 3 * progress + rng.gauss(0, 0.6))  # grows toward the deadline
            security = 0.0
            ast_sim = max(0.0, rng.gauss(22, 6))

            if anomalous and profile == "weak_tests":
                tests = rng.uniform(40, 70)
            if anomalous and profile == "plagiarized":
                ast_sim = rng.uniform(88, 99)
            if anomalous and profile == "insecure":
                security = float(rng.randint(1, 4))

            for metric_type, value in (
                ("TESTPASS", tests),
                ("CYCLO", cyclo),
                ("SECURITY", security),
                ("ASTSIM", ast_sim),
            ):
                value = round(value, 2)
                is_anom = anomalous and (
                    (profile == "weak_tests" and metric_type == "TESTPASS")
                    or (profile == "plagiarized" and metric_type == "ASTSIM")
                    or (profile == "insecure" and metric_type == "SECURITY")
                )
                records.append(
                    {
                        "project_code": code,
                        "profile": profile,
                        "metric_type": metric_type,
                        "value": value,
                        "iso_timestamp": ts,
                        "signature_hmac": signing.sign(code, metric_type, value, ts),
                        "anomaly_label": int(is_anom),
                    }
                )
    return records


def _packets(records: List[Dict]) -> Iterator:
    from grpc_service import tunisovereign_pb2 as pb2

    for r in records:
        yield pb2.TelemetryPacket(
            project_code=r["project_code"],
            metric_type=r["metric_type"],
            value=r["value"],
            iso_timestamp=r["iso_timestamp"],
            signature_hmac=r["signature_hmac"],
        )


def send_stream(records: List[Dict], target: str = "localhost:50051"):
    """Client-streaming RPC: push every record to the Django gRPC server."""
    import grpc

    from grpc_service import tunisovereign_pb2_grpc as pb2_grpc

    with grpc.insecure_channel(target) as channel:
        stub = pb2_grpc.TelemetryIngestServiceStub(channel)
        return stub.StreamTelemetry(_packets(records))


def send_urgent_audit(project_code: str, reason: str, target: str = "localhost:50051"):
    import grpc

    from grpc_service import tunisovereign_pb2 as pb2, tunisovereign_pb2_grpc as pb2_grpc

    with grpc.insecure_channel(target) as channel:
        stub = pb2_grpc.TelemetryIngestServiceStub(channel)
        return stub.TriggerUrgentAudit(pb2.AuditRequest(project_code=project_code, reason=reason))


def main():
    try:  # pick up GRPC_HMAC_SECRET from .env when run standalone
        from dotenv import load_dotenv
        from pathlib import Path

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="localhost:50051")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--projects", default=",".join(DEFAULT_PROJECTS))
    ap.add_argument("--dry-run", action="store_true", help="print a summary, do not send")
    ap.add_argument("--urgent", metavar="PROJECT_CODE", help="send one TriggerUrgentAudit instead")
    ap.add_argument("--reason", default="Manual urgent audit")
    args = ap.parse_args()

    if args.urgent:
        print(send_urgent_audit(args.urgent, args.reason, args.target))
        return

    records = generate_metrics(args.projects.split(","), args.days, args.seed)
    labelled = sum(r["anomaly_label"] for r in records)
    print(f"Generated {len(records)} signed packets (seed={args.seed}); {labelled} labelled anomalies.")
    if args.dry_run:
        for r in records[:5]:
            print(r)
        return
    ack = send_stream(records, args.target)
    print("Server ack:", ack)


if __name__ == "__main__":
    main()
