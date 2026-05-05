---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success']
inputDocuments:
  - docs/project-overview.md
  - docs/architecture.md
  - docs/source-tree-analysis.md
  - docs/component-inventory.md
  - docs/development-guide.md
  - docs/deployment-guide.md
  - README.md
  - CLAUDE.md
workflowType: 'prd'
classification:
  projectType: cli-tool
  domain: developer-tools
  complexity: medium-high
  projectContext: brownfield
features:
  - id: timeout-resilience
    priority: 1
    summary: Adaptive timeout + interactive decision forwarding
  - id: parallel-multi-project
    priority: 2
    summary: Each thread = separate project, run concurrently
  - id: usage-tracking
    priority: 3
    summary: /usage command to check credit/token consumption
  - id: voice-messages
    priority: 4
    summary: Voice → Whisper API → text → confirm → CLI
---

# Product Requirements Document - Chati

**Author:** Tony
**Date:** 2026-05-05

## Executive Summary

Chati is an intent-to-execution bridge that turns any messaging app into a developer workstation. It connects chat interfaces (currently Telegram) to AI coding CLIs (Kiro, Claude Code, Gemini, Codex), enabling developers to code, test, debug, and deploy from their phone — without opening a laptop.

The core problem: creative and productive moments don't follow a schedule. Ideas strike while driving, walking, or sitting at a cafe. The current developer workflow demands a laptop, an IDE, and focused screen time. Chati eliminates that friction by accepting natural language intent via chat (text or voice) and delegating execution to AI coding agents running on a persistent server.

v2 builds on a shipped v1.0.1 foundation (multi-CLI providers, streaming output, thread-based sessions, persistent PTY sessions) to address three critical gaps: reliability (adaptive timeout, interactive decision forwarding), productivity (parallel multi-project, usage tracking), and accessibility (voice messages with transcription confirmation).

### What Makes This Special

Chati is not a mobile IDE or a ChatGPT wrapper. It is a thin, fast bridge between human intent and AI-powered code execution. The differentiators:

1. **Ambient availability** — works from any device with a messaging app, no setup on the client side
2. **Real code execution** — AI agents read files, write code, run tests, take screenshots, deploy. Not just answering questions.
3. **Pluggable architecture** — adding a new AI CLI = one Python file. Adding a new chat platform = one module. Zero vendor lock-in.
4. **Persistent sessions** — PTY-based interactive sessions eliminate cold start overhead. Conversation context preserved across messages.
5. **Interactive decision forwarding** — when AI needs human judgment, the question surfaces on your phone with context. No more silent timeouts.

Long-term vision: evolve from developer tool into a universal intent-to-execution layer — where anyone with product authority (PM, designer, founder) can express intent in natural language and see it become shipped code.

## Project Classification

- **Project Type:** CLI tool / Developer productivity bot
- **Domain:** Developer tools
- **Complexity:** Medium-High (parallel subprocess orchestration, voice transcription, interactive state machine)
- **Project Context:** Brownfield — v1.0.1 shipped, adding features for v2.0
- **Target User:** Solo developer working across multiple projects (personal use first, community expansion later)
- **Platform:** Python 3.12+, Telegram (extensible to other chat platforms)

## Success Criteria

### User Success

- **Fire-and-forget workflow**: User sends voice/text message, walks away. Chati replies later with result + screenshot proof of completion. Zero babysitting required.
- **Laptop reduction**: User opens laptop 30% less than current baseline for coding tasks.
- **Decision continuity**: When CLI needs a decision, user sees the question with context on their phone within 10 seconds — not a silent timeout.
- **Multi-project flow**: User manages 3 active projects simultaneously via separate threads without context bleed or session conflicts.

### Business Success

- **Daily engagement**: 50+ messages/day across all projects (personal use baseline).
- **Active projects**: 3 concurrent projects with live sessions.
- **Community traction**: 1,000 GitHub stars within 6 months of public v2 release.
- **Timeout rate**: Reduced from 30% to <5% of all CLI interactions.

### Technical Success

- **Stream start latency**: <3s cold start (new session), <1s warm (existing session) — measured from message sent to first stream chunk visible.
- **Timeout rate**: <5% of interactions hit global timeout.
- **Voice transcription**: Whisper API response <2s for 5-15s audio clips.
- **Parallel stability**: 3 concurrent PTY sessions running without interference or resource exhaustion.
- **Screenshot delivery**: CLI-generated screenshots (via MCP browse tool) forwarded to Telegram as inline images.

### Measurable Outcomes

| Metric | Current (v1.0.1) | Target (v2.0) |
| ------ | ----------------- | ------------- |
| Stream start (cold) | ~6-10s | <3s |
| Stream start (warm) | ~3-4s | <1s |
| Timeout rate | ~30% | <5% |
| Concurrent projects | 1 | 3 |
| Voice support | None | Confirm-first flow |
| Decision forwarding | None | Auto-detect + forward |
| Screenshot proof | None | Inline image via MCP |

## Product Scope

### MVP — Minimum Viable Product

1. **Adaptive timeout** — reset deadline on each output chunk; pause deadline during decision wait
2. **Interactive decision forwarding** — detect CLI prompts via regex + idle threshold, forward to Telegram with context, pipe user answer back to PTY
3. **Parallel multi-project** — `/project` command binds project_dir per thread, each thread spawns independent PTY session
4. **Usage tracking** — `/usage` command parsing CLI credit/token output

### Growth Features (Post-MVP)

5. **Voice messages** — Whisper API transcription, confirm-first UX (✅ Send / ✏️ Edit / 🗑️ Cancel)
6. **Screenshot forwarding** — detect image files in CLI output, send as Telegram photos
7. **Driving mode** — voice-optimized responses (short, confirmation-heavy) when user indicates mobile context
8. **Session persistence** — survive bot restart without losing thread→project mapping

### Vision (Future)

- **Real-time voice call** — full-duplex voice conversation with AI agent (v3/v4)
- **Multi-platform** — Zalo, Messenger, Slack, Discord adapters
- **Intent-to-execution layer** — expand beyond developers to PM/designer/founder personas
- **Smart routing** — auto-select best CLI/model based on task type
- **Team features** — shared projects, role-based access, audit log
