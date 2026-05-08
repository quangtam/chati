# Story 3.1: Decision Prompt Detection (Hybrid Strategy)

Status: done

## Story

As a **system**,
I want to detect when the CLI subprocess is waiting for user input,
so that the question can be forwarded instead of silently timing out.

## Acceptance Criteria

1. `DecisionPrompt` dataclass (prompt_text, context_lines) in a shared location
2. Detection triggers: idle threshold (12s default) + last line matches pattern + last line ≤ 100 chars
3. Generic patterns: `[y/N]`, `[Y/n]`, `(yes/no)`, `(y/n)`, ends with `?`
4. Provider-specific patterns via optional `decision_prompt_patterns: list[re.Pattern]` on CliProvider ABC
5. Configurable via `DECISION_IDLE_THRESHOLD` env var
6. Detection respects message queued during DETECTING_PROMPT state (follow-up store as pending)
7. Unit tests pass with ≥80% branch coverage

## Tasks / Subtasks

- [ ] Task 1: Add `DecisionPrompt` dataclass to session_manager (or dedicated decision.py)
- [ ] Task 2: Add `decision_prompt_patterns` optional attr to CliProvider ABC
- [ ] Task 3: Implement `detect_decision_prompt(buffer_lines, provider)` utility
- [ ] Task 4: Add `DECISION_IDLE_THRESHOLD` config
- [ ] Task 5: Tests covering generic + provider-specific patterns + edge cases

## Dev Notes

### Location of DecisionPrompt

Add to `session_manager.py` since state machine references WAITING_FOR_USER — keeps related types together.

### Detection Algorithm

```python
def detect_decision_prompt(
    buffer_lines: list[str],
    provider_patterns: list[re.Pattern] | None = None,
) -> DecisionPrompt | None:
    """Analyze recent output lines to detect interactive prompt.
    
    Returns:
        DecisionPrompt if detected, None otherwise.
    """
    if not buffer_lines:
        return None
    
    last_line = buffer_lines[-1].rstrip("\n").strip()
    if not last_line or len(last_line) > 100:
        return None
    
    # Check generic patterns
    generic_patterns = [
        r"\[y/N\]", r"\[Y/n\]", r"\(yes/no\)", r"\(y/n\)",
    ]
    for pat in generic_patterns:
        if re.search(pat, last_line, re.IGNORECASE):
            return DecisionPrompt(
                prompt_text=last_line,
                context_lines=buffer_lines[-5:],
            )
    
    # Check provider-specific
    if provider_patterns:
        for pat in provider_patterns:
            if pat.search(last_line):
                return DecisionPrompt(
                    prompt_text=last_line,
                    context_lines=buffer_lines[-5:],
                )
    
    # Ends with ?
    if last_line.endswith("?"):
        return DecisionPrompt(
            prompt_text=last_line,
            context_lines=buffer_lines[-5:],
        )
    
    return None
```

### CliProvider Extension

Add to `cli_providers/base.py` as optional class attr (no ABC method change — backward compat):

```python
class CliProvider(ABC):
    # ...
    decision_prompt_patterns: list[re.Pattern] = []  # Optional override
```

### Config

```python
DECISION_IDLE_THRESHOLD = 12  # seconds before checking for prompt
```

### References

- [Source: architecture.md#Decision Forwarding Detection]
- [Source: epics.md#Story 3.1]

## Dev Agent Record

### Agent Model Used
Claude (Auto) via Kiro

### Completion Notes List

### File List
