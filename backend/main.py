"""CloudCritic FastAPI application.

Endpoints
---------
GET  /                  Serve frontend/index.html
GET  /health            Health check
GET  /api/pillars       List the 6 Well-Architected pillars and descriptions
POST /api/score         Score one architecture description (includes grade A-F)
POST /api/score/batch   Score multiple architecture descriptions
POST /api/explain       Plain-language LLM explanation of findings
"""

from __future__ import annotations

import pathlib
from typing import Any

from dotenv import load_dotenv
load_dotenv()  # loads .env into os.environ before any other module reads it

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from backend.models import Finding, Pillar, Severity
from backend.reviewer import explain_findings
from backend.scoring import score_architecture
# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CloudCritic",
    description="Score AWS architectures against the Well-Architected Framework.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ROOT       = pathlib.Path(__file__).parent.parent
_INDEX_HTML = _ROOT / "frontend" / "index.html"

# ---------------------------------------------------------------------------
# Pillar metadata  (read-only — no global mutable state)
# ---------------------------------------------------------------------------

_PILLAR_INFO: list[dict[str, str]] = [
    {"name": "Operational Excellence",  "description": "Run and monitor systems to deliver business value and continually improve processes."},
    {"name": "Security",                "description": "Protect data, systems, and assets through risk assessments and mitigation strategies."},
    {"name": "Reliability",             "description": "Recover from failures and dynamically acquire resources to meet demand."},
    {"name": "Performance Efficiency",  "description": "Use computing resources efficiently and maintain that efficiency as demand changes."},
    {"name": "Cost Optimization",       "description": "Avoid unnecessary costs and achieve the required capacity at the lowest price point."},
    {"name": "Sustainability",          "description": "Minimise environmental impact by reducing energy consumption and improving efficiency."},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
]

def _grade(aggregate: int) -> str:
    """Return letter grade A-F for an aggregate score 0-100."""
    for threshold, letter in _GRADE_THRESHOLDS:
        if aggregate >= threshold:
            return letter
    return "F"

def _findings_to_models(raw: list[dict[str, Any]]) -> list[Finding]:
    """Convert raw finding dicts from score_architecture into typed Finding instances."""
    return [
        Finding(
            pillar=Pillar(f["pillar"]),
            rule_id=f["rule_id"],
            severity=Severity(f["severity"]),
            impacted_components=tuple(f["impacted_components"]),
            description=f["description"],
            remediation=f.get(
                "remediation",
                f"No remediation guidance available for rule {f['rule_id']}",
            ),
        )
        for f in raw
    ]

def _score_with_grade(text: str) -> dict[str, Any]:
    """Run score_architecture and inject a grade field into the result."""
    result = score_architecture(text)
    result["grade"] = _grade(result["aggregate"])
    return result

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ArchitectureRequest(BaseModel):
    architecture: str = Field(..., min_length=1)

class BatchRequest(BaseModel):
    architectures: list[str] = Field(..., min_length=1)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    """Serve the single-page frontend."""
    if not _INDEX_HTML.is_file():
        raise HTTPException(status_code=404, detail="Frontend not built yet.")
    return FileResponse(str(_INDEX_HTML), media_type="text/html")

@app.get("/health")
def health() -> JSONResponse:
    """Health check for load balancers and uptime monitors."""
    return JSONResponse({"status": "ok", "version": "0.1.0"})

@app.get("/api/pillars")
def list_pillars() -> JSONResponse:
    """Return the six Well-Architected pillars with display names and descriptions."""
    return JSONResponse({"pillars": _PILLAR_INFO})

@app.post("/api/score")
def api_score(body: ArchitectureRequest) -> JSONResponse:
    """Score one architecture description.

    Returns pillar scores, aggregate, findings, and a letter grade (A-F).
    Grade thresholds: A >= 90, B >= 80, C >= 70, D >= 60, F otherwise.
    """
    try:
        return JSONResponse(_score_with_grade(body.architecture))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/score/batch")
def api_score_batch(body: BatchRequest) -> JSONResponse:
    """Score multiple architecture descriptions in one request.

    Returns results in the same order as the input list, each with the
    same shape as a single /api/score response.
    """
    try:
        results = [_score_with_grade(text) for text in body.architectures]
        return JSONResponse({"results": results})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post("/api/explain")
def api_explain(body: ArchitectureRequest) -> JSONResponse:
    """Return plain-language LLM advice for an architecture description.

    Scores the architecture first, then passes typed Finding objects to the
    reviewer. Falls back gracefully when OPENAI_API_KEY is absent.
    """
    try:
        result   = score_architecture(body.architecture)
        findings = _findings_to_models(result.get("findings", []))
        advice   = explain_findings(findings)
        return JSONResponse({"advice": advice})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
