"""Deterministic scoring logic for the CloudCritic Scoring Engine.

All functions are pure — no network calls, no randomness, no global mutable state.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Pillar score arithmetic
# ---------------------------------------------------------------------------

def compute_pillar_score(passing: int, total: int) -> int:
    """Return the pillar score as an integer in [0, 100].

    Uses round-half-up rounding: floor((passing / total) * 100 + 0.5).
    If *total* is 0 (no applicable rules for this pillar), returns 0.

    Args:
        passing: Number of rules that passed evaluation for this pillar.
        total:   Total number of rules evaluated for this pillar
                 (excludes rules that produced an internal error).

    Returns:
        An integer score in the inclusive range [0, 100].

    Examples:
        >>> compute_pillar_score(0, 10)
        0
        >>> compute_pillar_score(10, 10)
        100
        >>> compute_pillar_score(5, 10)
        50
        >>> compute_pillar_score(1, 3)
        33
        >>> compute_pillar_score(0, 0)
        0
    """
    if total == 0:
        return 0
    return math.floor((passing / total) * 100 + 0.5)

# ---------------------------------------------------------------------------
# Keyword-based rule catalog
# ---------------------------------------------------------------------------

# Each rule is (rule_id, keyword, severity, description).
# A rule passes when its keyword appears (case-insensitive) in the input text.
_RULES: list[tuple[str, str, str, str]] = [
    # Security
    ("SEC-001", "encryption",   "HIGH",     "Data at rest or in transit is not encrypted."),
    ("SEC-002", "iam",          "HIGH",     "No IAM-based access control detected."),
    ("SEC-003", "vpc",          "MEDIUM",   "Resources are not isolated within a VPC."),
    ("SEC-004", "waf",          "MEDIUM",   "No Web Application Firewall (WAF) detected."),
    ("SEC-005", "kms",          "MEDIUM",   "No KMS key management referenced for encryption."),
    # Reliability
    ("REL-001", "multi-az",     "CRITICAL", "No Multi-AZ deployment detected — single point of failure."),
    ("REL-002", "backup",       "HIGH",     "No backup strategy mentioned for data durability."),
    ("REL-003", "failover",     "HIGH",     "No failover mechanism detected."),
    ("REL-004", "health check", "MEDIUM",   "No health checks configured for service endpoints."),
    ("REL-005", "autoscaling",  "MEDIUM",   "No Auto Scaling policy detected for capacity management."),
    # Performance Efficiency
    ("PER-001", "cache",        "MEDIUM",   "No caching layer detected to reduce latency."),
    ("PER-002", "cdn",          "MEDIUM",   "No CDN referenced for static asset delivery."),
    ("PER-003", "cloudfront",   "MEDIUM",   "CloudFront not used for edge content delivery."),
    ("PER-004", "load balancer","HIGH",     "No load balancer detected for traffic distribution."),
    # Cost Optimization
    ("CST-001", "reserved",     "MEDIUM",   "No Reserved Instances or Savings Plans mentioned."),
    ("CST-002", "spot",         "LOW",      "Spot Instances not considered for fault-tolerant workloads."),
    ("CST-003", "savings plan", "MEDIUM",   "No Savings Plan referenced for compute cost reduction."),
    ("CST-004", "lifecycle",    "LOW",      "No S3 lifecycle policy detected for storage cost management."),
    # Operational Excellence
    ("OPS-001", "monitoring",   "HIGH",     "No monitoring strategy detected."),
    ("OPS-002", "cloudwatch",   "HIGH",     "CloudWatch not referenced for observability."),
    ("OPS-003", "logging",      "MEDIUM",   "No logging mechanism mentioned for audit trails."),
    ("OPS-004", "ci/cd",        "MEDIUM",   "No CI/CD pipeline detected for deployment automation."),
    ("OPS-005", "alarm",        "MEDIUM",   "No CloudWatch alarms configured for proactive alerting."),
    # Sustainability
    ("SUS-001", "graviton",     "LOW",      "Graviton processors not considered for energy efficiency."),
    ("SUS-002", "rightsizing",  "MEDIUM",   "No rightsizing strategy mentioned to reduce waste."),
    ("SUS-003", "serverless",   "MEDIUM",   "Serverless architecture not considered for sustainability."),
    ("SUS-004", "efficiency",   "LOW",      "No resource efficiency strategy referenced."),
]

# Map rule_id prefix → pillar display name
_PILLAR_MAP: dict[str, str] = {
    "SEC": "Security",
    "REL": "Reliability",
    "PER": "Performance Efficiency",
    "CST": "Cost Optimization",
    "OPS": "Operational Excellence",
    "SUS": "Sustainability",
}

# ---------------------------------------------------------------------------
# Public scoring function
# ---------------------------------------------------------------------------

def score_architecture(text: str) -> dict[str, Any]:
    """Score a plain-text architecture description against the Well-Architected pillars.

    Applies simple keyword-based deterministic rules (case-insensitive substring
    match). No network calls, no AI — the result depends only on *text* and the
    hard-coded rule catalog above.

    Args:
        text: Raw architecture description provided by the user.

    Returns:
        A JSON-serialisable dict::

            {
                "pillars": {
                    "<pillar_name>": {
                        "score":   int,   # 0-100
                        "passing": int,
                        "total":   int,
                    },
                    ...
                },
                "aggregate": int,
                "findings": [
                    {
                        "pillar":              str,
                        "rule_id":             str,
                        "severity":            str,
                        "description":         str,
                        "impacted_components": list[str],
                    },
                    ...  # sorted: severity desc, then pillar name asc
                ],
            }
    """
    lowered = text.lower()

    pillar_passing: dict[str, int] = {p: 0 for p in _PILLAR_MAP.values()}
    pillar_total: dict[str, int]   = {p: 0 for p in _PILLAR_MAP.values()}
    findings: list[dict[str, Any]] = []

    _severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    for rule_id, keyword, severity, description in _RULES:
        prefix = rule_id.split("-")[0]
        pillar = _PILLAR_MAP[prefix]
        pillar_total[pillar] += 1

        if keyword in lowered:
            pillar_passing[pillar] += 1
        else:
            findings.append({
                "pillar":              pillar,
                "rule_id":             rule_id,
                "severity":            severity,
                "description":         description,
                "impacted_components": ["architecture"],
            })

    pillars: dict[str, dict[str, int]] = {}
    for pillar in _PILLAR_MAP.values():
        passing = pillar_passing[pillar]
        total   = pillar_total[pillar]
        pillars[pillar] = {
            "score":   compute_pillar_score(passing, total),
            "passing": passing,
            "total":   total,
        }

    # Aggregate: equal-weighted mean, round-half-up.
    included = [v["score"] for v in pillars.values() if v["total"] > 0]
    aggregate = compute_pillar_score(sum(included), len(included) * 100) if included else 0

    # Sort: severity descending, pillar name ascending.
    findings.sort(key=lambda f: (_severity_order[f["severity"]], f["pillar"]))

    return {"pillars": pillars, "aggregate": aggregate, "findings": findings}
