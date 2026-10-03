---
inclusion: manual
---
<!------------------------------------------------------------------------------------
   This file is included only when invoked as a slash command (`/<filename>`)
   in chat. Use it for prompts and instructions you want to run on demand —
   the manual replacement for user-triggered hooks.

   Learn about inclusion modes: https://kiro.dev/docs/steering/#inclusion-modes
-------------------------------------------------------------------------------------> 
# Product Steering

## What CloudCritic is
A web app where a user pastes an AWS architecture description and gets:
- A score from 0 to 100 per Well-Architected pillar
- An aggregate score
- A prioritized list of concrete fixes

## Who it's for
Cloud engineers, students, and architects who want a quick sanity check on a design before building it.

## What it is NOT
- Not a live AWS account scanner
- Not a replacement for a real Well-Architected Review
- Not a chatbot

## Tone of output
Direct, specific, actionable. No filler. Every finding names the exact fix.

## Scope for this hackathon
- One-page frontend, one backend endpoint
- Deterministic scoring in plain Python
- AI used only to explain findings in plain language