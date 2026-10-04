"""LLM-powered plain-language reviewer for CloudCritic findings.

Calls the Groq Chat Completions API directly via ``requests`` (no SDK).
Groq exposes an OpenAI-compatible endpoint, so the request payload shape
is identical. Falls back to a deterministic summary when the API key is
absent or the request fails, so the module is always safe to call in
offline / CI contexts.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from models import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "openai/gpt-oss-120b"
_TIMEOUT_SECONDS = 30

_FALLBACK_TEMPLATE = (
    "LLM review unavailable (GROQ_API_KEY not set). "
    "{count} finding(s) detected: {summary}."
)

_SYSTEM_PROMPT = (
    "You are a senior AWS solutions architect reviewing a Well-Architected "
    "assessment. You will receive a JSON list of findings, each with a pillar, "
    "severity, description, and remediation guidance. "
    "Write a concise plain-language summary (no markdown, no bullet points) "
    "that a non-technical engineering manager can understand. "
    "Group observations by severity, highlight the most critical risks first, "
    "and close with one or two actionable next steps. "
    "Keep the response under 200 words."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_user_message(findings: list[Finding]) -> str:
    """Serialise *findings* to a compact JSON string for the user turn."""
    return json.dumps([f.to_dict() for f in findings], separators=(",", ":"))


def _deterministic_fallback(findings: list[Finding]) -> str:
    """Return a consistent plain-text summary without any LLM call.

    The output is derived solely from *findings*, so it is deterministic
    across invocations for the same input — safe for CI pipelines and
    snapshot tests.
    """
    if not findings:
        return (
            "LLM review unavailable (GROQ_API_KEY not set). "
            "No findings to report — architecture passed all evaluated rules."
        )

    # Group by severity for a structured fallback message.
    from collections import defaultdict

    by_severity: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        by_severity[f.severity.value].append(f.rule_id)

    parts: list[str] = []
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        ids = by_severity.get(level)
        if ids:
            parts.append(f"{len(ids)} {level}: {', '.join(ids)}")

    summary = "; ".join(parts)
    return _FALLBACK_TEMPLATE.format(count=len(findings), summary=summary)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def explain_findings(findings: list[Finding]) -> str:
    """Return a plain-language Groq LLM explanation of *findings*.

    Calls the Groq Chat Completions API using the key in
    ``os.environ["GROQ_API_KEY"]``.  If the key is absent, or if the
    request fails for any reason, a deterministic fallback message is
    returned instead — no exception is raised to the caller.

    Args:
        findings: List of :class:`~models.Finding` objects produced by the
                  scoring engine.  May be empty.

    Returns:
        A plain-text string suitable for display to an engineering manager.
        Never raises; network or auth failures are logged at WARNING level
        and the deterministic fallback is returned.

    Examples::

        advice = explain_findings(report.findings)
        print(advice)
    """
    api_key = os.environ.get("GROQ_API_KEY", "").strip()

    if not api_key:
        logger.debug("GROQ_API_KEY not set; returning deterministic fallback.")
        return _deterministic_fallback(findings)

    if not findings:
        return (
            "No findings to report — your architecture passed all evaluated rules."
        )

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(findings)},
        ],
        "temperature": 0,  # deterministic output
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            _GROQ_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        return body["choices"][0]["message"]["content"].strip()

    except requests.exceptions.Timeout:
        logger.warning(
            "Groq request timed out after %s seconds; returning fallback.",
            _TIMEOUT_SECONDS,
        )
    except requests.exceptions.HTTPError as exc:
        logger.warning(
            "Groq API returned HTTP %s: %s; returning fallback.",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except (requests.exceptions.RequestException, KeyError, ValueError) as exc:
        logger.warning("Groq request failed (%s); returning fallback.", exc)

    return _deterministic_fallback(findings)
