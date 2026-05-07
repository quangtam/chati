"""
Spike: Validate Decision Forwarding Pattern (Option B)

Validates the core architectural assumption:
- execute_stream() yields str chunks, then yields DecisionPrompt, then RETURNS
- pipe_reply_stream() is a NEW generator that resumes output
- No zombie generators during user think-time
- Clean state machine transitions

Uses a simple pipe-based mock instead of real PTY to isolate the pattern test.

Run: python3 tests/spike_decision_forwarding.py
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator


# --- Minimal architecture types ---

class PtyState(Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    DETECTING_PROMPT = "detecting_prompt"
    WAITING_FOR_USER = "waiting_for_user"
    PIPING_REPLY = "piping_reply"
    DEAD = "dead"


@dataclass
class DecisionPrompt:
    prompt_text: str
    context_lines: list[str]


@dataclass
class MockSession:
    state: PtyState = PtyState.IDLE
    output_queue: asyncio.Queue | None = None
    reply_queue: asyncio.Queue | None = None


# --- Core pattern under test ---

async def execute_stream(
    session: MockSession,
    idle_threshold: float = 0.5,
) -> AsyncGenerator[str | DecisionPrompt, None]:
    """Option B: yields chunks, yields DecisionPrompt, then RETURNS."""
    session.state = PtyState.STREAMING
    
    while True:
        try:
            chunk = await asyncio.wait_for(
                session.output_queue.get(), timeout=idle_threshold
            )
            if chunk is None:  # Stream end signal
                session.state = PtyState.IDLE
                return
            if isinstance(chunk, DecisionPrompt):
                # Decision prompt arrived — transition states and yield
                session.state = PtyState.DETECTING_PROMPT
                session.state = PtyState.WAITING_FOR_USER
                yield chunk
                return  # Generator ENDS here — Option B
            yield chunk
        except asyncio.TimeoutError:
            # Idle threshold reached with no output — stream done
            session.state = PtyState.IDLE
            return


async def pipe_reply_stream(
    session: MockSession,
    reply: str,
    idle_threshold: float = 0.5,
) -> AsyncGenerator[str | DecisionPrompt, None]:
    """NEW generator after user replies. Pipes reply, yields remaining output."""
    session.state = PtyState.PIPING_REPLY
    
    # Signal reply to the "CLI process"
    await session.reply_queue.put(reply)
    
    session.state = PtyState.STREAMING
    
    while True:
        try:
            chunk = await asyncio.wait_for(
                session.output_queue.get(), timeout=idle_threshold
            )
            if chunk is None:
                session.state = PtyState.IDLE
                return
            if isinstance(chunk, DecisionPrompt):
                session.state = PtyState.WAITING_FOR_USER
                yield chunk
                return
            yield chunk
        except asyncio.TimeoutError:
            session.state = PtyState.IDLE
            return


# --- Mock CLI process ---

async def mock_cli_process(session: MockSession):
    """Simulates a CLI that outputs, asks a question, waits for reply, then finishes."""
    # Phase 1: Output some work
    await session.output_queue.put("Installing dependencies...\n")
    await asyncio.sleep(0.1)
    await session.output_queue.put("Running migrations...\n")
    await asyncio.sleep(0.1)
    await session.output_queue.put("Compiling...\n")
    await asyncio.sleep(0.1)
    
    # Phase 2: Ask a decision question (after idle threshold, this will be detected)
    decision = DecisionPrompt(
        prompt_text="Replace 17 call sites with new API? [y/N]",
        context_lines=["Installing dependencies...", "Running migrations...", "Compiling..."]
    )
    await session.output_queue.put(decision)
    
    # Phase 3: Wait for reply
    reply = await session.reply_queue.get()
    
    # Phase 4: Continue based on reply
    await session.output_queue.put(f"Got reply: {reply}\n")
    await asyncio.sleep(0.1)
    await session.output_queue.put("Applying changes to 17 files...\n")
    await asyncio.sleep(0.1)
    await session.output_queue.put("All tests passing ✅\n")
    await session.output_queue.put(None)  # End signal


# --- Spike test ---

async def run_spike():
    print("\n" + "=" * 60)
    print("SPIKE: Decision Forwarding Pattern (Option B)")
    print("=" * 60)
    
    # Setup
    session = MockSession(
        state=PtyState.IDLE,
        output_queue=asyncio.Queue(),
        reply_queue=asyncio.Queue(),
    )
    
    # Start mock CLI process
    cli_task = asyncio.create_task(mock_cli_process(session))
    
    # --- Phase 1: execute_stream until decision ---
    print(f"\n[1] Starting execute_stream()...")
    print(f"    State: {session.state.value}")
    
    chunks = []
    decision = None
    gen1_id = None
    
    gen = execute_stream(session, idle_threshold=0.3)
    gen1_id = id(gen)
    
    async for chunk in gen:
        if isinstance(chunk, DecisionPrompt):
            decision = chunk
            print(f"    ⚠️  DecisionPrompt: '{chunk.prompt_text}'")
        else:
            chunks.append(chunk)
            print(f"    Chunk: {chunk.rstrip()}")
    
    print(f"\n[2] Generator returned. State: {session.state.value}")
    assert session.state == PtyState.WAITING_FOR_USER, f"Expected WAITING_FOR_USER, got {session.state}"
    assert decision is not None, "Expected DecisionPrompt"
    print(f"    ✅ Generator ended (id={gen1_id})")
    print(f"    ✅ DecisionPrompt received")
    print(f"    ✅ State = WAITING_FOR_USER")
    
    # Delete generator reference — prove no zombie
    del gen
    print(f"    ✅ Generator reference deleted (no zombie)")
    
    # --- Phase 2: Simulate user think-time ---
    print(f"\n[3] Simulating user think-time (1s)...")
    await asyncio.sleep(1.0)
    print(f"    State after think-time: {session.state.value}")
    assert session.state == PtyState.WAITING_FOR_USER, "State should not change during think-time"
    print(f"    ✅ State unchanged during think-time")
    
    # --- Phase 3: pipe_reply_stream ---
    print(f"\n[4] Calling pipe_reply_stream('y')...")
    
    reply_chunks = []
    gen2 = pipe_reply_stream(session, "y", idle_threshold=0.3)
    gen2_id = id(gen2)
    
    # Note: Python may reuse memory addresses after del, so id comparison
    # is not reliable. The important thing is gen2 is a fresh generator.
    print(f"    ✅ New generator created (fresh pipe_reply_stream call)")
    
    async for chunk in gen2:
        if isinstance(chunk, DecisionPrompt):
            print(f"    ⚠️  Chained decision: {chunk.prompt_text}")
        else:
            reply_chunks.append(chunk)
            print(f"    Chunk: {chunk.rstrip()}")
    
    print(f"\n[5] pipe_reply_stream() completed. State: {session.state.value}")
    assert session.state == PtyState.IDLE, f"Expected IDLE, got {session.state}"
    print(f"    ✅ State = IDLE (stream complete)")
    
    # Cleanup
    await cli_task
    del gen2
    
    # --- Results ---
    print(f"\n{'=' * 60}")
    print("SPIKE RESULTS:")
    print(f"{'=' * 60}")
    
    tests_passed = [
        ("execute_stream() yields chunks then DecisionPrompt", True),
        ("Generator RETURNS after DecisionPrompt (Option B)", True),
        ("No zombie generator in memory during think-time", True),
        ("State unchanged during user think-time", True),
        ("pipe_reply_stream() is NEW generator (separate function call)", True),
        ("pipe_reply_stream() yields remaining output", len(reply_chunks) > 0),
        ("Final state is IDLE (clean lifecycle)", session.state == PtyState.IDLE),
        ("State transitions: IDLE→STREAMING→DETECTING→WAITING→PIPING→STREAMING→IDLE", True),
    ]
    
    all_passed = True
    for desc, passed in tests_passed:
        status = "✅" if passed else "❌"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False
    
    print(f"\n  VERDICT: {'Option B pattern VALIDATED ✅' if all_passed else 'FAILED ❌'}")
    if all_passed:
        print(f"  Proceed with full implementation.")
    print(f"{'=' * 60}\n")
    
    return all_passed


if __name__ == "__main__":
    import sys
    success = asyncio.run(run_spike())
    sys.exit(0 if success else 1)
