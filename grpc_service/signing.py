"""HMAC-SHA256 packet signing shared by the gRPC server and the simulator client.

The secret comes from the GRPC_HMAC_SECRET environment variable (.env). A packet whose
signature does not match is rejected, so only trusted sandboxes can write metrics.
"""
import hashlib
import hmac
import os

DEFAULT_DEV_SECRET = "dev-only-change-me"


def get_secret() -> str:
    return os.getenv("GRPC_HMAC_SECRET", DEFAULT_DEV_SECRET)


def canonical(project_code: str, metric_type: str, value: float, iso_timestamp: str) -> str:
    return f"{project_code}|{metric_type}|{value:.4f}|{iso_timestamp}"


def sign(project_code: str, metric_type: str, value: float, iso_timestamp: str, secret: str = None) -> str:
    key = (secret if secret is not None else get_secret()).encode("utf-8")
    msg = canonical(project_code, metric_type, value, iso_timestamp).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify(project_code, metric_type, value, iso_timestamp, signature, secret: str = None) -> bool:
    expected = sign(project_code, metric_type, value, iso_timestamp, secret)
    return hmac.compare_digest(expected, signature or "")
