"""Deterministic scoring logic for the CloudCritic Scoring Engine.

All functions are pure — no network calls, no randomness, no global mutable state.
Rules are loaded at import time from backend/catalog/rules.json.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Load rule catalog
# ---------------------------------------------------------------------------

_CATALOG_PATH = Path(__file__).parent / "catalog" / "rules.json"

with _CATALOG_PATH.open(encoding="utf-8") as _f:
    _CATALOG: dict[str, Any] = json.load(_f)

_RULES: list[dict[str, Any]] = _CATALOG["rules"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_SEVERITY_WEIGHT: dict[str, int] = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Collect all pillar names preserving the first-seen order from the catalog.
_PILLARS: list[str] = list(dict.fromkeys(r["pillar"] for r in _RULES))

# ---------------------------------------------------------------------------
# Pillar score arithmetic
# ---------------------------------------------------------------------------

def compute_pillar_score(passing: int, total: int) -> int:
    """Return the pillar score as an integer in [0, 100].

    Uses round-half-up rounding: floor((passing / total) * 100 + 0.5).
    If *total* is 0 (no applicable rules for this pillar), returns 0.

    Args:
        passing: Numerator (e.g. sum of passing weights).
        total:   Denominator (e.g. sum of all weights for the pillar).

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
# Keyword matching
# ---------------------------------------------------------------------------

def _build_pattern(keyword: str, synonyms: list[str]) -> re.Pattern[str]:
    """Build a compiled regex that matches the keyword or any synonym.

    Uses word-boundary anchors (\\b) where the term starts/ends on a word
    character; falls back to plain substring for multi-word phrases that end
    on a non-word character (e.g. "at rest", "ci/cd").
    """
    terms = [keyword] + synonyms

    def _anchor(term: str) -> str:
        # Use \\b only when the boundary makes sense (alphanumeric edges).
        left  = r"\b" if re.match(r"\w", term[0])  else ""
        right = r"\b" if re.match(r"\w", term[-1]) else ""
        return left + re.escape(term) + right

    pattern = "|".join(_anchor(t) for t in terms)
    return re.compile(pattern, re.IGNORECASE)


# Pre-compile one pattern per rule at import time for performance.
_RULE_PATTERNS: list[re.Pattern[str]] = [
    _build_pattern(r["keyword"], r.get("synonyms", []))
    for r in _RULES
]

# ---------------------------------------------------------------------------
# Public scoring function
# ---------------------------------------------------------------------------

def score_architecture(text: str) -> dict[str, Any]:
    """Score a plain-text architecture description against the Well-Architected pillars.

    Applies keyword + synonym regex matching (case-insensitive, word-boundary
    aware). Pillar scores are severity-weighted: each rule contributes its
    weight (CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1) to both the numerator (if
    passing) and denominator.

    Args:
        text: Raw architecture description provided by the user.

    Returns:
        A JSON-serialisable dict::

            {
                "pillars": {
                    "<pillar_name>": {
                        "score":   int,   # 0-100
                        "passing": int,   # sum of passing weights
                        "total":   int,   # sum of all weights for this pillar
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
                        "remediation":         str,
                        "doc_url":             str,
                        "impacted_components": list[str],
                    },
                    ...  # sorted: severity desc, then pillar name asc
                ],
            }
    """
    pillar_passing: dict[str, int] = {p: 0 for p in _PILLARS}
    pillar_total:   dict[str, int] = {p: 0 for p in _PILLARS}
    findings: list[dict[str, Any]] = []

    for rule, pattern in zip(_RULES, _RULE_PATTERNS):
        pillar    = rule["pillar"]
        severity  = rule["severity"]
        weight    = _SEVERITY_WEIGHT[severity]

        pillar_total[pillar] += weight

        if pattern.search(text):
            pillar_passing[pillar] += weight
        else:
            findings.append({
                "pillar":              pillar,
                "rule_id":             rule["rule_id"],
                "severity":            severity,
                "description":         rule["description"],
                "remediation":         rule.get("remediation", ""),
                "doc_url":             rule.get("doc_url", ""),
                "impacted_components": ["architecture"],
            })

    pillars: dict[str, dict[str, int]] = {}
    for pillar in _PILLARS:
        passing = pillar_passing[pillar]
        total   = pillar_total[pillar]
        pillars[pillar] = {
            "score":   compute_pillar_score(passing, total),
            "passing": passing,
            "total":   total,
        }

    # Aggregate: equal-weighted mean of pillar scores, round-half-up.
    included = [v["score"] for v in pillars.values() if v["total"] > 0]
    aggregate = compute_pillar_score(sum(included), len(included) * 100) if included else 0

    # Sort findings: severity descending, then pillar name ascending.
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f["severity"]], f["pillar"]))

    return {"pillars": pillars, "aggregate": aggregate, "findings": findings}
