"""Threshold rules turning a raw metric into an AuditFinding (Track 6 thresholds).

Spec (Track 6): zero high-severity Bandit/Semgrep findings, tests pass >= 85 %,
anomaly on a plagiarised AST signature or a vulnerable pattern.
These deterministic rules run at ingestion time; the IsolationForest module (Week 2)
adds statistical detection on top of them.
"""
from typing import NamedTuple, Optional

from .models import AnalysisMetric, AuditFinding

AST_PLAGIARISM_THRESHOLD_PCT = 85.0
CYCLOMATIC_WARNING_THRESHOLD = 15.0

MT = AnalysisMetric.MetricType
FT = AuditFinding.FindingType
SV = AuditFinding.Severity


class FindingSpec(NamedTuple):
    finding_type: str
    severity: str
    description: str


def evaluate_metric(cohort, metric_type: str, value: float) -> Optional[FindingSpec]:
    """Return the finding to open for this metric value, or None if it is within limits."""
    if metric_type == MT.TEST_PASS and value < cohort.min_test_pass_pct:
        return FindingSpec(
            FT.LOW_TEST_COVERAGE,
            SV.MEDIUM,
            f"Test pass rate {value:.1f}% is below the cohort minimum of {cohort.min_test_pass_pct:.1f}%.",
        )
    if metric_type == MT.SECURITY_SCORE and value > cohort.max_high_severity_findings:
        return FindingSpec(
            FT.OTHER,
            SV.CRITICAL,
            f"{int(value)} high-severity Bandit/Semgrep finding(s); the cohort allows "
            f"{cohort.max_high_severity_findings}.",
        )
    if metric_type == MT.AST_SIMILARITY and value >= AST_PLAGIARISM_THRESHOLD_PCT:
        return FindingSpec(
            FT.AST_PLAGIARISM,
            SV.CRITICAL,
            f"AST similarity {value:.1f}% reaches the plagiarism threshold of {AST_PLAGIARISM_THRESHOLD_PCT:.0f}%.",
        )
    if metric_type == MT.CYCLOMATIC and value > CYCLOMATIC_WARNING_THRESHOLD:
        return FindingSpec(
            FT.OTHER,
            SV.LOW,
            f"Cyclomatic complexity {value:.1f} exceeds the recommended maximum of {CYCLOMATIC_WARNING_THRESHOLD:.0f}.",
        )
    return None
