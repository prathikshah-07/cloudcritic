"""CloudCritic FastAPI app."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import scoring, reviewer
from backend.models import Finding

app = FastAPI(title="CloudCritic")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


class ScoreRequest(BaseModel):
    architecture: str


@app.get("/")
def index():
    if not FRONTEND.exists():
        return {"status": "ok", "note": "frontend not built yet"}
    return FileResponse(FRONTEND)


@app.post("/api/score")
def api_score(req: ScoreRequest):
    try:
        return scoring.score_architecture(req.architecture)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/explain")
def api_explain(req: ScoreRequest):
    try:
        report = scoring.score_architecture(req.architecture)
        findings = [Finding(**f) for f in report.get("findings", [])]
        return {"explanation": reviewer.explain_findings(findings)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))