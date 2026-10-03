---
inclusion: manual
---
<!------------------------------------------------------------------------------------
   This file is included only when invoked as a slash command (`/<filename>`)
   in chat. Use it for prompts and instructions you want to run on demand —
   the manual replacement for user-triggered hooks.

   Learn about inclusion modes: https://kiro.dev/docs/steering/#inclusion-modes
-------------------------------------------------------------------------------------> 
# Project Structure

## Layout
- .kiro/ — specs, steering, hooks, agents, MCP config
- backend/ — FastAPI app: main.py, reviewer.py, scoring.py, models.py
- frontend/ — single HTML page (index.html) served by FastAPI
- tests/ — pytest + hypothesis tests
- examples/ — sample architecture descriptions (good, bad, serverless)

## Rules
- backend/scoring.py is pure deterministic Python — no AI, no network
- backend/reviewer.py handles all AI calls
- Never import reviewer from scoring
- All paths relative to repo root