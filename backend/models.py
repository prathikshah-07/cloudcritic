"""Domain models for the CloudCritic Scoring Engine.

All dataclasses are frozen (immutable) to guarantee determinism across
evaluation runs and thread-safe concurrent usage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Pillar(str, Enum):
    """The six AWS Well-Architected Framework pillars."""

    OPERATIONAL_EXCELLENCE = "Operational Excellence"
    SECURITY = "Security"
    RELIABILITY = "Reliability"
    PERFORMANCE_EFFICIENCY = "Performance Efficiency"
    COST_OPTIMIZATION = "Cost Optimization"
    SUSTAINABILITY = "Sustainability"


class Severity(str, Enum):
    """Impact classification for a Finding.

    Ordered from most to least severe; ``sort_key()`` returns a numeric
    value suitable for ascending sort (0 = most severe).
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    def sort_key(self) -> int:
        """Return a numeric sort key where 0 is the highest severity."""
        _order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }
        return _order[self]


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A gap identified when a rule fails evaluation.

    Attributes:
        pillar:               The Well-Architected pillar the rule belongs to.
        rule_id:              Unique identifier of the failed rule (e.g. ``"SEC-001"``).
        severity:             Impact classification of this gap.
        impacted_components:  Tuple of component names from the architecture
                              description that triggered the failure (≥ 1).
        description:          Human-readable explanation of the gap (≥ 10 words).
        remediation:          Concrete fix recommendation referencing at least one
                              AWS service or Well-Architected best practice.
                              Falls back to
                              ``"No remediation guidance available for rule <rule_id>"``
                              when the rule catalog carries no remediation text.
    """

    pillar: Pillar
    rule_id: str
    severity: Severity
    impacted_components: tuple[str, ...]
    description: str
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return {
            "pillar": self.pillar.value,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "impacted_components": list(self.impacted_components),
            "description": self.description,
            "remediation": self.remediation,
        }


# ---------------------------------------------------------------------------
# PillarScore
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PillarScore:
    """Score and rule counts for a single Well-Architected pillar.

    Attributes:
        pillar:        The pillar being scored.
        score:         Integer score in the inclusive range [0, 100].
        passing_rules: Number of rules that passed evaluation.
        total_rules:   Number of rules evaluated (excluding errored rules).
    """

    pillar: Pillar
    score: int
    passing_rules: int
    total_rules: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return {
            "pillar": self.pillar.value,
            "score": self.score,
            "passing_rules": self.passing_rules,
            "total_rules": self.total_rules,
        }


# ---------------------------------------------------------------------------
# EvaluationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationReport:
    """Complete output of a single scoring engine run.

    Attributes:
        rule_catalog_version: Semver string of the Rule Catalog used
                              (e.g. ``"1.0.0"``).
        schema_version:       Semver string of this report's schema format
                              (e.g. ``"1.0.0"``).
        pillar_scores:        Mapping from :class:`Pillar` to
                              :class:`PillarScore` for every included pillar.
        aggregate_score:      Weighted average of all included pillar scores,
                              rounded to the nearest integer (round-half-up),
                              in the inclusive range [0, 100].
        total_rules:          Total rules evaluated across all pillars.
        passing_rules:        Rules that passed evaluation.
        failing_rules:        Rules that failed evaluation.
        excluded_pillars:     List of dicts describing pillars excluded from
                              scoring, each with keys ``"pillar"`` and
                              ``"reason"``.
        error_rules:          Rule IDs that raised an internal exception during
                              evaluation and were excluded from scoring.
        findings:             Findings sorted by severity (CRITICAL first) then
                              pillar name ascending.
    """

    rule_catalog_version: str
    schema_version: str
    pillar_scores: dict[Pillar, PillarScore]
    aggregate_score: int
    total_rules: int
    passing_rules: int
    failing_rules: int
    excluded_pillars: tuple[dict[str, str], ...]
    error_rules: tuple[str, ...]
    findings: tuple[Finding, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation.

        The returned dict can be passed directly to :func:`json.dumps` without
        any custom encoder.  Keys are in a stable, human-readable order.
        """
        return {
            "aggregate_score": self.aggregate_score,
            "error_rules": list(self.error_rules),
            "excluded_pillars": list(self.excluded_pillars),
            "failing_rules": self.failing_rules,
            "findings": [f.to_dict() for f in self.findings],
            "passing_rules": self.passing_rules,
            "pillar_scores": {
                pillar.value: ps.to_dict()
                for pillar, ps in self.pillar_scores.items()
            },
            "rule_catalog_version": self.rule_catalog_version,
            "schema_version": self.schema_version,
            "total_rules": self.total_rules,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to canonical JSON with sorted keys and *indent* spaces.

        Args:
            indent: Number of spaces used for indentation (default 2).

        Returns:
            A UTF-8 JSON string with keys sorted in ascending alphabetical
            order, suitable for deterministic comparison and audit trails.
        """
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent)
