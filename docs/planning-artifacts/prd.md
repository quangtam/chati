---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-01b-continue', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
completedAt: '2026-05-06'
releaseMode: phased
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
    summary: Each thread = separate project, run concurrently with SQLite-persisted config
  - id: cli-info
    priority: 3
    summary: /info command — full CLI context, session stats, best-effort usage tracking
  - id: voice-messages
    priority: growth
    summary: Voice input (Whisper) + voice output (TTS), deferred to Growth phase
---

# Product Requirements Document - Chati

**Author:** Tony
**Date:** 2026-05-05

## Executive Summary

Chati is an intent-to-execution bridge that turns any messaging app into a developer workstation. It connects chat interfaces (currently Telegram) to AI coding CLIs (Kiro, Claude Code, Gemini, Codex), enabling developers to code, test, debug, and deploy from their phone — without opening a laptop.

The core problem: creative and productive moments don't follow a schedule. Ideas strike while driving, walking, or sitting at a cafe. The current developer workflow demands a laptop, an IDE, and focused screen time. Chati eliminates that friction by accepting natural language intent via chat (text or voice) and delegating execution to AI coding agents running on a persistent server.

v2 builds on a shipped v1.0.1 foundation (multi-CLI providers, streaming output, thread-based sessions, persistent PTY sessions) to address three critical gaps: reliability (adaptive timeout, interactive decision forwarding), productivity (parallel multi-project, unified CLI info), and visibility (per-thread session state, usage tracking). Voice I/O and screenshot forwarding are planned for the Growth phase after MVP stabilizes.

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
- **Voice transcription**: Whisper API response <3s for 5-15s audio clips (Growth).
- **Parallel stability**: Up to 3 concurrent PTY sessions per user running without interference; system supports up to 5 concurrent sessions total.
- **Screenshot delivery**: CLI-generated screenshots (via MCP browse tool) forwarded to Telegram as inline images (Growth).

### Measurable Outcomes

| Metric | Current (v1.0.1) | Target (v2.0) |
| ------ | ----------------- | ------------- |
| Stream start (cold) | ~6-10s | <3s (MVP) |
| Stream start (warm) | ~3-4s | <1s (MVP) |
| Timeout rate | ~30% | <5% (MVP) |
| Concurrent projects per user | 1 | 3 (MVP) |
| Voice I/O | None | Whisper in + TTS out, confirm-first (Growth) |
| Decision forwarding | None | Auto-detect + forward (MVP) |
| Screenshot proof | None | Inline image via MCP (Growth) |

## User Journeys

The following journeys translate Chati's value proposition — *"code from your pocket"* — into concrete narrative arcs. Each journey surfaces capabilities that v2.0 must deliver.

### Journey 1 — Ambient Coder, Happy Path

**Persona: Minh, 28, full-stack developer, Da Nang**

Minh runs a solo SaaS on the side. He has a day job, a toddler at home, and roughly two uninterrupted hours per week to push his side project forward. His backlog is full of small, well-scoped tasks — exactly the kind of work AI CLIs excel at, if only he had a keyboard in front of him.

**Opening Scene.** Saturday, 10:42 AM. Minh is at a café waiting for his flat white. He remembers the sprint board has three P2 bugs he triaged last night. Today's goal: close at least one. On his phone, he opens Telegram, taps the `#sidehustle-billing` thread (already bound to his billing microservice via `/project`), and sends a voice message:

> "Check sprint status, then pick up the top P2 bug and fix it. Run the tests when done. Screenshot the passing suite."

**Rising Action.** Chati shows a confirmation card: *"Transcription ✓ / Edit ✏️ / Cancel 🗑️."* Minh taps ✓. The bot replies `⏳ Connecting...`, then starts streaming: sprint status loaded → top P2 identified → file opened → patch applied → `pytest` running. The stream pauses mid-flight — no output for 45 seconds — but the message doesn't time out. The adaptive timeout keeps resetting as the test suite churns. Minh pockets his phone, grabs his coffee, walks out to the waterfront.

**Climax.** Nine minutes later, his phone buzzes. A screenshot of a green `pytest` summary appears inline in the thread. Below it:

> ✅ BUG-2317 fixed. 14 tests passing. Branch `fix/duplicate-invoice-race` pushed. Ready for PR?

**Resolution.** Minh replies "yes". Chati opens the PR and forwards the link. Minh tucks his phone away and keeps walking. He closed a bug without touching his laptop, and he still has 50 minutes of weekend left.

**Capabilities this journey reveals:**
- Voice message → Whisper transcription → confirm-first UX
- Per-thread `project_dir` binding (`/project`) with persistent session
- Adaptive timeout (resets on each output chunk)
- Inline screenshot forwarding from CLI tools to Telegram
- Conversational follow-up within an active session (`"yes"` → PR opened)

### Journey 2 — Decision Forwarding, Interruption Path

**Persona: Minh again, mid-task**

Minh has given Chati a multi-step task ("upgrade the stripe library and adapt the breaking changes") and stepped into a Grab ride to his co-working space. He's not driving — he's in the back seat, phone in hand, but he doesn't want to babysit.

**Opening Scene.** The stream shows `pip install stripe==9.0.0 --upgrade` running in the background. Then: silence. Twelve seconds pass. Normally Minh would worry the session died.

**Rising Action.** A new message arrives in the thread:

> ⚠️ **CLI is waiting for input.** Detected prompt:
>
> ```
> The new stripe 9.x removes the `invoice.pay()` helper.
> Replace all 17 call sites with `invoice.pay_and_close()`? [y/N]
> ```
> Context: I've already staged the library upgrade. Reply **y** to proceed or **n** to abort and revert.

The bot has detected an interactive prompt via regex match + idle threshold, paused its own timeout clock, and surfaced the question with enough context to decide without scrolling back.

**Climax.** Minh replies "y". Chati pipes `y\n` back into the PTY. The stream resumes. Two minutes later, all 17 call sites are migrated, tests pass, and a diff summary lands in the thread.

**Resolution.** Minh arrives at his co-working space. He hasn't opened his laptop once. He didn't lose the session to a silent timeout. The AI made the boring 80% of the decision; Minh owned the 20% that required judgment. He moves on to his next task.

**Capabilities this journey reveals:**
- Interactive prompt detection (regex + idle threshold)
- Forwarding question + surrounding context from PTY to chat
- Piping user reply back into PTY fd
- Timeout pause during wait-for-human state
- Resumption without breaking streaming state machine

### Journey 3 — Parallel Multi-Project Flow

**Persona: Minh, running three projects in parallel**

It's a Sunday afternoon. Minh is catching up: one thread for his billing microservice, one for his blog (a static site he's been migrating to Astro), and one for an open-source library he maintains. Today, all three need attention.

**Opening Scene.** Minh opens Telegram. His bot chat has three active threads. He sends different commands in each:

- `#billing` → "Retry the failed CI run."
- `#blog` → "Draft a post about the flight home — photos are in `~/Pictures/2026-trip`."
- `#osslib` → "Triage new issues from this week and label them."

**Rising Action.** Three PTY sessions spawn in parallel, one per thread. Each has its own `project_dir` binding, its own CLI provider (Minh uses Kiro for code, Claude for prose), its own session history. Minh glances at each thread — they're all streaming independently. No context bleed. No lock contention. He flips between threads like browsing separate Slack channels.

**Climax.** Halfway through, Minh wants to know how much Kiro credit he's burning. In `#billing` he sends `/info`. Chati replies:

> 💳 Kiro (this thread): 142K tokens this session • 2.8M tokens this month
> 📊 Monthly quota: 73% used • Resets in 11 days

Reassured, he keeps going.

**Resolution.** By evening, all three tasks are done. The sessions are still warm — next week, when Minh wants to continue, Chati will resume each thread where it left off, even if the bot has restarted in between.

**Capabilities this journey reveals:**
- Thread-scoped `project_dir` + provider + model state
- Concurrent PTY sessions without cross-thread interference
- `/info` command showing CLI context, session stats, and best-effort credit/token usage
- Session persistence surviving bot restarts (thread ↔ project mapping)
- Mixed-provider operation (different threads, different CLIs)

### Journey 4 — Community Adopter, First-Time Setup

**Persona: Linh, 24, junior backend engineer, Hanoi**

Linh saw the Chati demo video on Twitter. She's been looking for a way to use Claude Code without paying for Cursor, and the "messaging app as IDE" pitch caught her. She has a Raspberry Pi at home and a Telegram account.

**Opening Scene.** 9:00 PM, Linh clones the repo on her Pi over SSH:

```
git clone https://github.com/quangtam/chati.git && cd chati && bash setup.sh
```

**Rising Action.** The wizard asks questions in order: Python version check (pass), which CLI (she picks Claude because she already has `claude login` working on the Pi), Telegram bot token (she creates one via @BotFather in 90 seconds), her Telegram user ID (she uses @userinfobot), project directory. The wizard writes `.env`. No more than three minutes.

`./chati start`. The log shows `Starting Chati / CLI Provider: claude / Ready for messages`. She opens her bot in Telegram, sends `/start`, sees a welcome card. She sends `/help`, scans the commands. She tries her first real message:

> "What does `cli_runner.py` do? Summarize in three bullets."

**Climax.** Eight seconds later (cold start), the first chunk streams in. Three bullets appear, followed by a clean closing message. No ANSI garbage. No credits footer. Just the answer.

Linh sends a follow-up: *"Show me the PTY session lifecycle as a diagram."* Chati replies with an ASCII diagram. The thread now feels like a conversation, not a prompt box.

**Resolution.** Linh writes a short tweet: *"Got Chati running on my Pi in under 10 min. This is the mobile dev tool I've been waiting for. ⭐ starred."* One more star for the 1,000-star v2 goal. She goes to sleep thinking about which bug to tackle from bed tomorrow morning.

**Capabilities this journey reveals:**
- Zero-to-first-message onboarding under 10 minutes
- Setup wizard (`setup.sh`) with CLI auto-detect and `.env` generation
- Process management (`./chati start|stop|restart|status|log`)
- `/start` and `/help` command UX (first impressions)
- Output pipeline: ANSI strip → extract response → MD→HTML → clean chat render
- First-message stream-start latency target (<3s warm, <8s truly-cold with Pi-class hardware)

### Journey Requirements Summary

The four journeys together map to the following capability areas, which the v2.0 functional requirements must cover:

| Capability Area | Required By Journey(s) | MVP / Growth |
| --------------- | ---------------------- | ------------ |
| Adaptive timeout (reset-on-chunk, pause-on-wait) | J1, J2 | MVP |
| Interactive decision detection + forwarding + reply piping | J2 | MVP |
| Thread-bound `project_dir` + per-thread session isolation | J3 | MVP |
| `/info` command with CLI context + best-effort credit parsing | J3 | MVP |
| Voice input → Whisper → confirm-first UX | J1 | Growth |
| Inline screenshot forwarding from CLI tool output | J1 | Growth |
| Session persistence across bot restart | J3 | Growth |
| Onboarding: setup wizard + login guides + `/start` / `/help` polish | J4 | MVP (already shipped v1, polish only) |
| Output pipeline: ANSI strip + response extraction + MD→HTML | J1, J4 | Maintained from v1 |
| Process management scripts | J4 | Maintained from v1 |

Each MVP feature in the PRD frontmatter (`timeout-resilience`, `parallel-multi-project`, `cli-info`) is justified by at least one journey. The `voice-messages` feature is deferred to the Growth phase. No journey requires a capability that is not planned for v2.0 or already shipped in v1.

## CLI Tool Specific Requirements

### Command Structure (v2.0)

Chati exposes commands via Telegram slash-command interface. Users interact through messaging, not a terminal shell.

#### Existing Commands (v1.0.1 — maintained)

| Command | Purpose |
| ------- | ------- |
| `/start` | Welcome message with project info |
| `/help` | Usage guide |
| `/model` | Select AI model (inline keyboard) |
| `/skills` | List available BMAD skills |
| `/status` | Check CLI activity for current thread (upgraded: shows process state in parallel context) |
| `/cancel` | Kill running CLI for current thread (unchanged — works per-thread in parallel mode) |
| `/new` | Reset session for current thread |
| `/resume` | Resume previous session |
| `/bmad_*` | BMAD skill routing (underscore → hyphen) |

#### New Commands (v2.0)

| Command | Purpose | Scope |
| ------- | ------- | ----- |
| `/project <path>` | Bind current thread to a project directory. Validates path exists on server. Rejects if path not found. Handles paths with spaces (entire text after `/project ` is the path). | MVP |
| `/projects` | List previously-used project directories for quick re-binding. User selects via inline keyboard — no path typing on phone. | MVP |
| `/info` | Show CLI session info: provider name, logged-in user (if detectable), model, session duration, messages sent this session. Credit/token usage = best-effort per-provider (explicitly marked "may not be available for all providers"). | MVP |
| `/provider <name>` | Switch CLI provider for current thread (persisted). **Rejects if active process running** — user must `/cancel` first. Validates provider name against registry. | MVP |
| `/sessions` | List all active threads with status indicators: 🟢 active / ⏳ waiting for input / 💤 idle / ❌ dead. Shows bound project, provider, model per thread. Paginated if >10 threads. | MVP |

#### Command Design Principles

- All commands are thread-aware — they operate on the current thread's context
- State-changing commands (`/project`, `/provider`, `/model`) persist to SQLite
- Informational commands (`/info`, `/sessions`, `/status`) are read-only
- `/provider` is guarded — cannot switch mid-execution to prevent orphaned processes
- Free-form text is always forwarded to the active CLI session

### Output Formats

Chati transforms CLI subprocess output into Telegram-native formats:

| Output Type | Telegram Format | Source | Notes |
| ----------- | --------------- | ------ | ----- |
| Text response | HTML message (headings, code, tables, lists) | CLI stdout → ANSI strip → MD→HTML pipeline | |
| Long response | Auto-split into multiple 4096-char messages | `split_message()` at natural boundaries | |
| Screenshots | Inline photo (`sendPhoto`) | CLI tool output (e.g., MCP browse screenshots) | Fallback to document attachment if >10MB |
| Voice response | Voice message (OGG opus via TTS) | AI-generated response → TTS API | **Skip for code-heavy responses** (>50% code blocks) — send text only |
| Streaming preview | Edited message every 1.5s | Progressive stdout buffering | |
| Decision prompt | Formatted message with context + reply instruction | Interactive prompt detection | |
| Error | Plain text with error context | Subprocess stderr or timeout | |

#### Voice Response (v2.0 — Growth)

- Text response synthesized via TTS API, sent as Telegram voice message
- **Content filtering**: responses with >50% code block content skip TTS (code is unlistenable)
- Text version always sent alongside voice (accessibility + reference)
- Useful for hands-free scenarios (walking, commuting)

### Configuration Schema

#### Static Configuration (`.env` — unchanged)

Global defaults loaded at startup. Same as v1.0.1 with no structural changes:

```
TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, CLI_PROVIDER (default),
PROJECT_DIR (default), CLI_TIMEOUT (default), CLI_TRUST_ALL_TOOLS, LOG_LEVEL
```

#### Dynamic Configuration (SQLite — new in v2.0)

Per-thread state persisted across bot restarts:

```sql
CREATE TABLE thread_config (
    thread_id       INTEGER PRIMARY KEY,
    project_dir     TEXT NOT NULL,
    cli_provider    TEXT,              -- NULL = use .env CLI_PROVIDER
    model           TEXT,              -- NULL = use provider default
    timeout_seconds INTEGER,           -- NULL = use .env CLI_TIMEOUT
    last_active_at  TEXT,              -- last message activity timestamp
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

**Resolution order:** `thread_config` column → `.env` global default → provider hardcoded default.

**Clarification on provider switch:** When user runs `/provider claude` but has no model set, model resolves as: thread_config.model (NULL) → `.env` default model (if set) → claude provider's hardcoded default. There is no provider-specific `.env` layer — keep it simple.

#### SQLite Technical Requirements

- **WAL mode mandatory**: `PRAGMA journal_mode=WAL` — enables concurrent reads during writes
- **Busy timeout**: `PRAGMA busy_timeout=5000` — prevents "database is locked" under parallel thread writes
- **Async access**: Use `aiosqlite` library — do not share connections across coroutines
- **Migration**: On first v2.0 startup, if no SQLite DB exists, create it. Existing single-project behavior preserved (default thread uses `.env PROJECT_DIR`)
- **File location**: `chati.db` in project root (alongside `chati.log`, `.chati.pid`)

#### Why SQLite

- Zero external dependencies (Python stdlib `sqlite3` + `aiosqlite` for async)
- Single-file database — easy backup, easy inspect
- Survives bot restart (unlike in-memory dicts)
- Fast enough for <100 threads (no concurrent write pressure with WAL)
- Familiar to contributors

### Scripting & Automation Support

Chati is not a scriptable CLI itself — it's a bot process. However, it supports automation patterns:

| Pattern | Mechanism |
| ------- | --------- |
| Headless operation | `nohup` / systemd / Docker — no TTY required |
| Process management | `./chati start\|stop\|restart\|status\|log` scripts |
| Health monitoring | Exit code from `./chati status`; log pattern matching |
| Scheduled messages | External cron → Telegram Bot API `sendMessage` → triggers Chati handler |
| Bulk config | Edit `.env` + restart; or direct SQLite manipulation for thread configs |

### Sections Explicitly Out of Scope

Per project-type guidance, the following are **not applicable** to Chati and will not be documented:

- Visual design system (no UI beyond Telegram's native rendering)
- UX principles for touch interactions (Telegram handles all touch UX)
- Shell completion (users interact via Telegram, not a terminal)

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-solving MVP — deliver the minimum that eliminates the three biggest pain points of v1.0.1 (silent timeouts, single-project limitation, no visibility into CLI state). Voice and media features deferred to Growth phase to keep MVP lean and shippable within a focused sprint.

**Resource Requirements:** Solo developer (Tony), leveraging AI coding CLIs for implementation. No external dependencies beyond existing tech stack + `aiosqlite`.

**Core Principle:** Every MVP feature must be usable via text input on a phone. No feature requires voice, media, or external API beyond Telegram + CLI subprocess.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported in MVP:**
- Journey 2 (Decision Forwarding) — fully supported
- Journey 3 (Parallel Multi-Project) — fully supported
- Journey 4 (Community Adopter) — onboarding maintained from v1, enhanced with `/projects`
- Journey 1 (Ambient Coder) — partially supported (text-only; voice input and screenshot forwarding ship in Growth)

**Must-Have Capabilities:**

| # | Feature | Description | Justification |
|---|---------|-------------|---------------|
| 1 | Adaptive timeout | Reset deadline on each output chunk; pause during decision-wait state | Eliminates 30% timeout rate → <5% |
| 2 | Interactive decision forwarding | Detect CLI prompts (regex + idle threshold), forward with context, pipe reply back to PTY | Enables fire-and-forget workflow |
| 3 | Parallel multi-project | `/project`, `/projects`, `/provider`, `/sessions`, SQLite thread_config, concurrent PTY sessions | Enables 3 simultaneous projects |
| 4 | `/info` command | Provider, user, model, session stats, best-effort token usage | Visibility into CLI state |
| 5 | SQLite persistence | thread_config table with WAL mode, `aiosqlite` | Thread state survives restart |
| 6 | Enhanced `/status` | Show per-thread process state (active/waiting/idle/dead) | Parallel session visibility |

**Dependencies:** Feature 3 depends on Feature 5 (SQLite). Feature 2 depends on Feature 1 (timeout pause). Features 4 and 6 are independent.

### Growth Features (Phase 2)

Ship after MVP is validated and stable in daily use.

| # | Feature | Description | Depends On |
|---|---------|-------------|------------|
| 1 | Voice input | Whisper API transcription → confirm-first UX (✅/✏️/🗑️) | MVP stable |
| 2 | Voice output | TTS response as OGG opus voice message (skip for code-heavy) | Voice input |
| 3 | Screenshot forwarding | Detect image files in CLI output → send as inline Telegram photo | MVP stable |
| 4 | PTY session reconnect | Serialize session state → survive bot restart → reconnect warm sessions | SQLite (MVP) |
| 5 | Driving mode | Voice-optimized responses (short, confirmation-heavy) when user indicates mobile context | Voice I/O |

### Vision Features (Phase 3+)

Long-term direction, not committed to timeline.

- Real-time voice call — full-duplex voice conversation with AI agent
- Multi-platform — Zalo, Messenger, Slack, Discord adapters
- Intent-to-execution layer — expand beyond developers to PM/designer/founder personas
- Smart routing — auto-select best CLI/model based on task type
- Team features — shared projects, role-based access, audit log

### Risk Mitigation Strategy

**Technical Risks:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Interactive prompt detection false positives/negatives | Decision forwarding unreliable | Start with conservative regex + high idle threshold (12s). Tune based on real usage. Provide `/cancel` escape hatch. |
| SQLite contention under parallel writes | "database is locked" errors | WAL mode + busy_timeout=5000 + per-operation connections via `aiosqlite`. Tested sufficient for <100 threads. |
| PTY session leaks with parallel processes | Memory/process exhaustion | Max 5 concurrent sessions (configurable). Idle session cleanup after 30min. `/sessions` shows resource state. |
| `/info` token parsing breaks on CLI updates | Stale/wrong usage data | Best-effort with explicit "may not be available" disclaimer. Bot-tracked metrics (messages, duration) always reliable. |

**Market Risks:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users prefer native mobile IDE (Cursor mobile, etc.) | Low adoption | Chati's value is zero-setup client side + pluggable CLI. Validate with community feedback before Growth investment. |
| AI CLI landscape shifts (new tools, deprecated tools) | Provider rot | Pluggable architecture (1 file = 1 provider). Community can contribute new providers. |

**Resource Risks:**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Solo developer bandwidth | Slow delivery | MVP scoped to 6 features (4 new capabilities + SQLite infrastructure + enhanced status). AI-assisted development (dogfooding Chati to build Chati). |
| Scope creep from community requests | MVP delayed | Strict MVP boundary. Growth features tracked but not committed until MVP ships. |

## Functional Requirements

### Session & Process Management

- FR1: User can send free-form text messages that are forwarded to the active CLI session in the current thread
- FR2: User can start a new CLI session for the current thread, discarding previous conversation context
- FR3: User can resume a previous CLI session in the current thread
- FR4: User can cancel a running CLI process in the current thread without affecting other threads
- FR5: System can maintain multiple concurrent PTY sessions (up to 5) across different threads without interference
- FR6: System can detect when a PTY session has died and report its status accurately
- FR7: User can view all active sessions with per-thread status indicators (active, waiting for input, idle, dead)

### Adaptive Timeout & Reliability

- FR8: System can reset the idle timeout deadline each time new output is received from the CLI subprocess
- FR9: System can pause the timeout clock when an interactive decision prompt is detected
- FR10: System can resume the timeout clock after the user responds to a decision prompt
- FR11: System can warn the user when a session has been idle beyond a configurable threshold
- FR12: User can configure per-thread timeout overrides that persist across bot restarts

### Interactive Decision Forwarding

- FR13: System can detect when the CLI subprocess is waiting for user input (via regex pattern matching + idle threshold)
- FR14: System can forward the detected prompt to the user with surrounding context sufficient to make a decision
- FR15: User can reply to a forwarded decision prompt and have their response piped back into the PTY subprocess
- FR16: System can resume normal streaming after the user's reply is delivered to the subprocess

### Multi-Project Management

- FR17: User can bind the current thread to a specific project directory on the server
- FR18: System can validate that a specified project directory exists before accepting the binding
- FR19: User can browse previously-used project directories and select one for re-binding without typing the path
- FR20: User can switch the CLI provider for the current thread (when no active process is running)
- FR21: User can select an AI model for the current thread via inline keyboard
- FR22: System can persist thread configuration (project_dir, provider, model, timeout) in SQLite across bot restarts
- FR23: System can resolve configuration using fallback chain: thread-specific → global default → provider default

### CLI Information & Monitoring

- FR24: User can view current session information including provider name, logged-in user (if detectable), active model, session duration, and messages sent
- FR25: System can display best-effort token/credit usage when the CLI provider supports it
- FR26: User can check CLI binary availability and authentication status
- FR27: User can view a help guide listing all available commands and their usage

### Output Processing & Delivery

- FR28: System can strip ANSI escape sequences from CLI output and convert Markdown to Telegram HTML
- FR29: System can split messages exceeding 4096 characters at natural boundaries (paragraph, line, space)
- FR30: System can stream CLI output progressively by editing a preview message at regular intervals
- FR31: System can send typing indicators while CLI is processing
- FR32: System can forward CLI-generated screenshot files as inline Telegram photos (with fallback to document for >10MB)

### Voice Communication (Growth)

- FR33: User can send a voice message that is transcribed to text via speech-to-text API
- FR34: System can present transcription to user for confirmation before forwarding to CLI (confirm / edit / cancel)
- FR35: System can synthesize text responses into voice messages (OGG opus format) sent via Telegram
- FR36: System can detect code-heavy responses (>50% code blocks) and skip voice synthesis, sending text only
- FR37: System can send text version alongside voice response for accessibility and reference

### Authentication & Security

- FR38: System can restrict bot access to a whitelist of authorized Telegram user IDs

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Stream start latency (cold — new PTY session) | <3 seconds | Time from message sent to first stream chunk visible in Telegram |
| Stream start latency (warm — existing session) | <1 second | Time from message sent to first stream chunk visible |
| Stream preview update interval | 1.5 seconds | Time between progressive message edits |
| Decision prompt detection | <12 seconds idle threshold | Time from last CLI output to forwarding prompt to user |
| Decision reply delivery | <500ms | Time from user reply to piping into PTY fd |
| `/info` response | <2 seconds | Time from command to full info display |
| `/sessions` response | <2 seconds | Time from command to session list render |
| `/projects` inline keyboard | <1 second | Time from command to keyboard display |
| SQLite read operations | <50ms | Any single SELECT query |
| SQLite write operations | <200ms | Any single INSERT/UPDATE (including WAL flush) |
| Voice transcription (Growth) | <3 seconds | Whisper API response for 5-15s audio clips |
| Voice synthesis (Growth) | <4 seconds | TTS API response for typical text response |

**Concurrent load:** System must handle 5 simultaneous PTY sessions streaming output without degradation. Each session's stream-start latency must remain within target regardless of other active sessions.

### Security

**Authentication & Authorization:**
- All bot interactions gated by `ALLOWED_USER_IDS` whitelist — unauthorized users receive no response
- Telegram Bot token stored exclusively in `.env` (never logged, never committed)
- API keys (Whisper, TTS, CLI providers) stored in `.env` with file permissions `600`

**Trust Boundary:**
- `CLI_TRUST_ALL_TOOLS` setting explicitly documented as security trade-off
- When `true`: AI CLI can read/write any file in `PROJECT_DIR`, run shell commands, install packages
- `PROJECT_DIR` must never point to `/`, `~`, or directories containing secrets outside the project
- Bot must not forward raw `.env` content or API keys in any Telegram message

**Prompt Injection Mitigation:**
- User input forwarded to CLI as-is (no sanitization — CLI's own safety layer handles this)
- Bot does not execute commands from CLI output — only forwards text/images to user
- Decision forwarding displays CLI prompt verbatim but does not auto-execute suggested actions

**Log Security:**
- `chati.log` file permissions: `600` (owner read/write only)
- Logs must not contain raw API keys or Telegram bot token
- Log rotation: 7-day retention, older logs deleted automatically
- SQLite database file permissions: `600`

**Network:**
- Outbound HTTPS only: `api.telegram.org`, CLI-specific API endpoints, Whisper/TTS APIs (Growth)
- No inbound connections required (long polling, not webhook)
- No data sent to third parties beyond Telegram API and configured CLI/voice APIs

### Reliability

**Availability:**
- Target: 99% uptime (≤7.3 hours downtime per month)
- Auto-restart on crash via systemd `Restart=on-failure` with `RestartSec=10`
- Health check: `./chati status` returns exit code 0 when process alive and polling
- Alerting: log pattern monitoring for `ERROR`, `409 Conflict`, `timed out`

**Crash Recovery:**
- Bot restart must not lose thread→project bindings (SQLite persists)
- Active PTY sessions are lost on crash — user informed on next message ("Session expired, starting fresh")
- No data corruption: SQLite WAL mode ensures atomic writes even on unexpected termination
- PID file cleanup on startup if stale (prevents "already running" false positive)

**Process Lifecycle:**
- Maximum 5 concurrent PTY sessions (configurable via `.env`)
- Idle session cleanup: sessions with no activity for 30 minutes are killed and resources freed
- Orphan process detection: on startup, scan for leftover CLI processes from previous run and kill them
- Memory monitoring: log warning if RSS exceeds 500MB (indicates session leak)

**Graceful Degradation:**
- If CLI binary not found: inform user with clear error, suggest checking installation
- If Telegram API rate-limited: back off message edits, increase `_STREAM_UPDATE_INTERVAL`
- If SQLite locked: retry with exponential backoff (up to busy_timeout=5000ms)
- If Whisper/TTS API unavailable (Growth): fallback to text-only, notify user "voice temporarily unavailable"

### Integration

**Telegram Bot API:**
- Protocol: HTTPS long polling (not webhook)
- Rate limits respected: max 30 message edits/minute/chat, 20 messages/second globally
- Message size: 4096 characters max (auto-split for longer content)
- Media: photos up to 10MB via `sendPhoto`, documents up to 50MB via `sendDocument`
- Inline keyboards for `/model`, `/projects` selection

**CLI Subprocess Integration:**
- Protocol: PTY (pseudo-terminal) via `pty.fork()` for interactive sessions
- Fallback: `asyncio.subprocess` with `stdin=DEVNULL` for non-interactive providers
- Output encoding: UTF-8 assumed, ANSI escape sequences stripped
- Process signals: SIGTERM for graceful kill, SIGKILL after 5s if unresponsive

**SQLite (v2.0):**
- Library: `aiosqlite` for async access
- Journal mode: WAL (mandatory)
- Connection pattern: per-operation connection (no shared connection across coroutines)
- Schema migration: version check on startup, auto-create tables if missing

**External APIs (Growth phase):**
- Whisper API: OpenAI speech-to-text, audio format OGG from Telegram voice messages
- TTS API: text-to-speech synthesis, output OGG opus for Telegram voice messages
- Both APIs: timeout 10s, graceful fallback to text on failure, no retry (user can resend)
