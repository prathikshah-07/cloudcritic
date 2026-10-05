# CloudCritic

**A deterministic AWS Well-Architected Framework reviewer with an LLM narrator.**

CloudCritic scores any plain-text architecture description against 26 curated rules
across the six Well-Architected pillars — deterministically, with no AI in the
scoring path. Then it uses a Groq-hosted LLM to explain the findings in plain
English and answer follow-up remediation questions, streaming the answer live
to the browser.

The score is reproducible. The explanation is conversational. The two never
touch each other.

---

## Why it's different

- **Deterministic core.** Same architecture → same score, every time. No LLM
  judge, no nondeterminism, no hallucinated grade. Audit-friendly.
- **Grounded AI.** The model always receives the precomputed findings and rule
  IDs. It is instructed to answer only about this architecture. No fabricated
  critiques.
- **Never-raise contract.** Every AI endpoint has a hand-written deterministic
  fallback. Missing API key, network failure, timeouts, partial streams — the
  user always gets a useful answer.
- **Real-time streaming.** Explanations and chat replies stream token by token
  from Groq, through FastAPI's `StreamingResponse`, to the browser's
  `ReadableStream`. No buffering, no waiting for a full paragraph.

---

## Features

### Deterministic scoring engine
- 26 rules across the 6 Well-Architected pillars
- Severity-weighted: CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1
- Case-insensitive keyword + synonym regex, word-boundary aware
- Per-pillar scores (0–100) plus an aggregate score and letter grade (A–F)
- Findings sorted by severity descending, then pillar name ascending
- Zero network calls in the core

### API
| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/`               | Serve the single-page frontend |
| `GET`  | `/health`         | Health check |
| `GET`  | `/api/pillars`    | List the 6 pillars and their descriptions |
| `POST` | `/api/score`      | Score one architecture |
| `POST` | `/api/score/batch`| Score many architectures |
| `POST` | `/api/explain`    | Stream a plain-English explanation |
| `POST` | `/api/chat`       | Stream a conversational remediation reply |

### LLM integration (Groq)
- Model: `openai/gpt-oss-120b` (configurable via `GROQ_MODEL`)
- OpenAI-compatible streaming SSE
- `reasoning_effort: "low"` keeps thinking tokens small so the visible answer
  is never truncated by the output budget
- Two scoped system prompts — one for explanations, one for chat
- Payload caps: architecture text, chat history, findings count, field length

### Reliability
- Deterministic fallback on every AI endpoint
- Partial-stream interruption notice instead of duplicated fallback
- History validation — only `user`/`assistant` turns with string content pass
- Graceful degradation when `GROQ_API_KEY` is absent

### Frontend
- Single HTML file, vanilla JS, no build step
- Animated aggregate score with letter grade and color coding
- Pillar grid with animated progress bars
- Severity summary pills
- Findings list with severity badges and rule IDs
- Streaming "Explain in plain English"
- "Ask the architect" chat panel with suggestion chips, typing indicator,
  history, streamed replies, and inline retry

---

## Quick start

```bash
# 1. Clone and enter
git clone <your-repo-url>
cd cloudcritic

# 2. Create a virtualenv
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your Groq key
cp .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_...

# 5. Run
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000/** in your browser.

---

## Configuration

Environment variables (read from `.env` at the project root):

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(none)* | Groq API key. If absent, all AI endpoints return deterministic fallbacks. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model name. |
| `GROQ_REASONING_EFFORT` | `low` | Reasoning effort for gpt-oss models. |

---

## Project layout

```
cloudcritic/
├── backend/
│   ├── main.py                 # FastAPI routes
│   ├── models.py               # Finding, PillarScore, EvaluationReport
│   ├── reviewer.py             # Groq streaming + deterministic fallbacks
│   ├── scoring.py              # Deterministic scoring engine
│   └── catalog/
│       └── rules.json          # 26 rules across 6 pillars
├── frontend/
│   └── index.html              # Single-file UI (vanilla JS, no build)
├── tests/
│   └── property/               # Hypothesis property tests
├── examples/                   # Example architectures
├── requirements.txt
├── .env.example
└── README.md
```

---

## How scoring works

1. For each of the 26 rules, compile a regex from the rule's `keyword` and
   `synonyms` (case-insensitive, word-boundary aware).
2. For each rule, test the architecture text. Match → rule passes; no match →
   rule fails and a finding is created.
3. Sum severity weights for passing rules and total weights per pillar.
4. `pillar_score = floor(passing_weight / total_weight * 100 + 0.5)`.
5. `aggregate = floor(mean(pillar_scores))`.
6. Letter grade: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F otherwise.
7. Sort findings by severity descending, then pillar name ascending.

The engine is pure: no network, no randomness, no global mutable state.

---

## How AI narration works

1. `POST /api/explain` (or `/api/chat`) runs the deterministic scorer first.
2. The findings are placed into a system prompt alongside the architecture text.
3. The prompt instructs the model to answer only about this architecture,
   cite specific rule IDs, give concrete AWS-specific fixes, and stay short.
4. The model is streamed via Groq's OpenAI-compatible SSE endpoint.
5. Chunks are forwarded token by token to the browser through FastAPI's
   `StreamingResponse`.
6. On any failure before output has been shown, a deterministic fallback is
   streamed instead. On failure after partial output, a short interruption
   notice is appended. The endpoint never raises to the browser.

---

## Testing

```bash
pytest
```

Property tests use Hypothesis to verify invariants on the scoring engine —
monotonicity, bounds, and reproducibility across runs.

---

## License

MIT
