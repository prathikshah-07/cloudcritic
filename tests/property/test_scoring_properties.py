"""Property-based tests for backend/scoring.py using Hypothesis."""

import pytest
from hypothesis import given, settings

from backend.scoring import compute_pillar_score, score_architecture
from tests.strategies import architecture_text

_VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@given(architecture_text)
@settings(max_examples=100)
def test_pillar_score_bounds(text: str) -> None:
    """Property 1: Every pillar score returned by score_architecture is in [0, 100]."""
    result = score_architecture(text)
    for pillar_name, data in result["pillars"].items():
        score = data["score"]
        assert 0 <= score <= 100, (
            f"Pillar '{pillar_name}' score {score} out of bounds for input {text!r}"
        )


@given(architecture_text)
@settings(max_examples=100)
def test_aggregate_score_bounds(text: str) -> None:
    """Property 2: The aggregate score returned by score_architecture is in [0, 100]."""
    result = score_architecture(text)
    aggregate = result["aggregate"]
    assert 0 <= aggregate <= 100, (
        f"Aggregate score {aggregate} out of bounds for input {text!r}"
    )


@given(architecture_text)
@settings(max_examples=100)
def test_determinism(text: str) -> None:
    """Property 3: score_architecture returns identical output for the same input."""
    first = score_architecture(text)
    second = score_architecture(text)
    assert first == second, (
        f"Non-deterministic result for input {text!r}:\nfirst={first}\nsecond={second}"
    )


@given(architecture_text)
@settings(max_examples=100)
def test_findings_correspondence(text: str) -> None:
    """Property 4: Every finding has a severity in VALID_SEVERITIES and a non-empty rule_id."""
    result = score_architecture(text)
    for finding in result["findings"]:
        assert finding["severity"] in _VALID_SEVERITIES, (
            f"Unknown severity {finding['severity']!r} in finding {finding}"
        )
        assert finding["rule_id"], (
            f"Empty rule_id in finding {finding}"
        )


@given(architecture_text)
@settings(max_examples=100)
def test_findings_sort_order(text: str) -> None:
    """Property 5: Findings are sorted by severity CRITICAL→HIGH→MEDIUM→LOW, then pillar name ascending."""
    result = score_architecture(text)
    findings = result["findings"]
    for i in range(len(findings) - 1):
        a, b = findings[i], findings[i + 1]
        ord_a = _SEVERITY_ORDER[a["severity"]]
        ord_b = _SEVERITY_ORDER[b["severity"]]
        assert ord_a < ord_b or (
            ord_a == ord_b and a["pillar"] <= b["pillar"]
        ), (
            f"Sort order violated at index {i}: "
            f"{a['severity']}/{a['pillar']} before {b['severity']}/{b['pillar']}"
        )
