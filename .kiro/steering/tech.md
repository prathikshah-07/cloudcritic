# Tech Steering

## Stack
- Python 3.11+
- FastAPI for the backend
- Pydantic v2 for validation
- pytest + hypothesis for tests

## Conventions
- Type hints on every function
- No global mutable state
- No secrets in code — use .env
- Every commit message starts with a prefix: spec, feat, fix, test, docs, chore

## Rules
- Never add dependencies without a reason
- Never commit .env, __pycache__, or .venv
- Keep files under 300 lines