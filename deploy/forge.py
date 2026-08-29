#!/usr/bin/env python3
"""
Swap & Forge: session lifecycle management for Claude Code.

Swap = hot reload: trim transcript, resume. Context survives, crons stay.
Forge = cold restart: full restart with minimal retained context.
Auto = check conditions and pick swap vs forge vs skip.

Usage:
  python3 forge.py --auto              # auto-detect: swap, forge, or skip
  python3 forge.py --swap              # force swap
  python3 forge.py                     # force forge (legacy behavior)
  python3 forge.py --dry-run           # preview without executing
  python3 forge.py --status            # show transcript stats
"""

import json
import os
import sys
import uuid
import glob
import subprocess
import time
from pathlib import Path

CANDIDATE_PROJECT_DIRS = [
    "/root/.claude/projects/-root-ombre",
    "/root/.claude/projects/-root",
]

PROJECT_DIR = None  # resolved dynamically by find_active_session()
ARCHIVE_DIR = None

# Forge: cold restart, keep less
FORGE_RETAIN_TOKENS = 80000
FORGE_MIN_EVENTS = 2000

# Swap: hot reload, keep less to stay light
SWAP_RETAIN_TOKENS = 50000
SWAP_MIN_EVENTS = 800

# Auto-detection thresholds
SWAP_TRIGGER_TOKENS = 160000   # swap before system auto-compression (~200k)
SWAP_BEFORE_FORGE = 5          # forge after this many swaps
FORGE_TRIGGER_FILES = ["CLAUDE.md", ".claude/settings.json"]

KEEPABLE_TYPES = {"user", "assistant", "mode", "permission-mode"}
SKIP_TYPES = {"queue-operation", "file-history-snapshot", "last-prompt", "ai-title", "attachment", "system"}


def find_active_session():
    """Find the most recently modified transcript across all candidate project dirs."""
    global PROJECT_DIR, ARCHIVE_DIR
    all_jsonls = []
    for d in CANDIDATE_PROJECT_DIRS:
        all_jsonls.extend(glob.glob(os.path.join(d, "*.jsonl")))
    if not all_jsonls:
        return None
    best = max(all_jsonls, key=os.path.getmtime)
    PROJECT_DIR = os.path.dirname(best)
    ARCHIVE_DIR = os.path.join(PROJECT_DIR, "archive")
    return best


def read_jsonl(path):
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def strip_thinking(event):
    """Remove thinking blocks from assistant messages to save tokens."""
    msg = event.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return event
    new_content = [c for c in content if c.get("type") != "thinking"]
    if len(new_content) != len(content):
        event = dict(event)
        event["message"] = dict(msg, content=new_content)
    return event


def is_heavy_event(event, max_chars=3000):
    """Check if event contains heavy content: large tool_results, images, base64."""
    msg = event.get("message", {})
    content = msg.get("content", [])
    if not isinstance(content, list):
        return False
    for block in content:
        btype = block.get("type", "")
        # Large tool results
        if btype == "tool_result":
            result_content = block.get("content", "")
            if isinstance(result_content, list):
                result_text = json.dumps(result_content, ensure_ascii=False)
            else:
                result_text = str(result_content)
            if len(result_text) > max_chars:
                return True
        # Images (base64 encoded)
        if btype == "image":
            return True
        # Any block with base64 source
        source = block.get("source", {})
        if isinstance(source, dict) and source.get("type") == "base64":
            return True
    return False


def filter_keepable(events):
    """Keep only meaningful events, strip thinking, skip huge tool results."""
    keepable = []
    for e in events:
        t = e.get("type", "")
        if t not in KEEPABLE_TYPES:
            continue
        # Skip heavy events: large tool results, base64 images, etc
        if is_heavy_event(e):
            continue
        # Strip thinking blocks from assistant messages
        if t == "assistant":
            e = strip_thinking(e)
            # Skip empty assistant events (thinking-only)
            msg = e.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list) and not content:
                continue
        keepable.append(e)
    return keepable


def estimate_tokens(event):
    """Rough token estimate for an event."""
    msg = event.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, list):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    return int(len(text) / 2.4)


def find_clean_boundary(events, retain_tokens):
    """Find a cut point that keeps ~retain_tokens worth of recent events,
    landing on a user message boundary (start of a turn)."""
    total = 0
    cut_candidates = []

    for i in range(len(events) - 1, -1, -1):
        total += estimate_tokens(events[i])
        if events[i].get("type") == "user":
            msg = events[i].get("message", {})
            content = msg.get("content", "")
            is_tool_result = isinstance(content, list) and any(
                c.get("type") == "tool_result" for c in content
            )
            if not is_tool_result:
                cut_candidates.append((i, total))
        if total > retain_tokens and cut_candidates:
            break

    if not cut_candidates:
        return 0

    # Pick the last candidate that's still under the budget,
    # or the first one if all exceed it
    under_budget = [c for c in cut_candidates if c[1] <= retain_tokens]
    if under_budget:
        return under_budget[-1][0]  # deepest cut that fits in budget
    return cut_candidates[0][0]  # smallest available


def ensure_tool_primer(events):
    """Make sure tool_use and tool_result pairs are complete.
    Remove orphaned tool_results at the start and orphaned tool_uses at the end."""
    if not events:
        return events

    # Find tool_use IDs in assistant messages
    tool_use_ids = set()
    tool_result_ids = set()

    for e in events:
        msg = e.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                tool_use_ids.add(block.get("id"))
            elif block.get("type") == "tool_result":
                tool_result_ids.add(block.get("tool_use_id"))

    # Remove events with orphaned tool_results (no matching tool_use)
    orphaned_results = tool_result_ids - tool_use_ids
    if orphaned_results:
        cleaned = []
        for e in events:
            msg = e.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                has_orphan = any(
                    c.get("type") == "tool_result" and c.get("tool_use_id") in orphaned_results
                    for c in content
                )
                if has_orphan:
                    # Filter out the orphaned tool_result blocks
                    new_content = [
                        c for c in content
                        if not (c.get("type") == "tool_result" and c.get("tool_use_id") in orphaned_results)
                    ]
                    if new_content:
                        e = dict(e)
                        e["message"] = dict(msg, content=new_content)
                        cleaned.append(e)
                    continue
            cleaned.append(e)
        events = cleaned

    return events


def rewrite_session_chain(events, new_sid):
    """Rewrite sessionId and uuid chain for the new session."""
    uuid_map = {}
    rewritten = []

    for e in events:
        e = dict(e)

        old_uuid = e.get("uuid")
        if old_uuid:
            new_uuid = str(uuid.uuid4())
            uuid_map[old_uuid] = new_uuid
            e["uuid"] = new_uuid

        parent = e.get("parentUuid")
        if parent and parent in uuid_map:
            e["parentUuid"] = uuid_map[parent]
        elif parent:
            e["parentUuid"] = ""

        if "sessionId" in e:
            e["sessionId"] = new_sid

        # Rewrite sourceToolAssistantUUID
        source = e.get("sourceToolAssistantUUID")
        if source and source in uuid_map:
            e["sourceToolAssistantUUID"] = uuid_map[source]

        rewritten.append(e)

    return rewritten


def write_jsonl(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def verify_transcript_growth(path, timeout=30):
    """Wait for the transcript file to grow (CC is writing to it)."""
    initial_size = os.path.getsize(path) if os.path.exists(path) else 0
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(2)
        current_size = os.path.getsize(path) if os.path.exists(path) else 0
        if current_size > initial_size + 100:
            return True
    return False


def mark_last_good(sid):
    """Save the session ID as last-good for recovery."""
    with open(os.path.join(PROJECT_DIR, ".last-good"), "w") as f:
        f.write(sid)


def archive_old(path):
    """Move old transcript to archive."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    name = os.path.basename(path)
    os.rename(path, os.path.join(ARCHIVE_DIR, name))


def get_transcript_stats(session_path):
    """Get stats about the current transcript."""
    events = read_jsonl(session_path)
    keepable = filter_keepable(events)
    total_tokens = sum(estimate_tokens(e) for e in keepable)
    return {
        "path": session_path,
        "total_events": len(events),
        "keepable_events": len(keepable),
        "estimated_tokens": total_tokens,
    }


def get_swap_count():
    path = os.path.join(PROJECT_DIR, ".swap-count")
    if os.path.exists(path):
        try:
            return int(open(path).read().strip())
        except (ValueError, IOError):
            pass
    return 0


def increment_swap_count():
    path = os.path.join(PROJECT_DIR, ".swap-count")
    count = get_swap_count() + 1
    with open(path, "w") as f:
        f.write(str(count))
    return count


def reset_swap_count():
    path = os.path.join(PROJECT_DIR, ".swap-count")
    with open(path, "w") as f:
        f.write("0")


def check_code_changes():
    """Check if key config files changed since last forge/swap."""
    marker = os.path.join(PROJECT_DIR, ".last-forge-commit")
    last_commit = ""
    if os.path.exists(marker):
        with open(marker) as f:
            last_commit = f.read().strip()

    try:
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd="/root/ombre", stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return False

    if not last_commit or last_commit == current:
        return False

    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", last_commit, current],
            cwd="/root/ombre", stderr=subprocess.DEVNULL
        ).decode().strip().split("\n")
    except Exception:
        return False

    return any(f in changed for f in FORGE_TRIGGER_FILES)


def mark_forge_commit():
    """Record current git commit for change detection."""
    try:
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd="/root/ombre", stderr=subprocess.DEVNULL
        ).decode().strip()
        with open(os.path.join(PROJECT_DIR, ".last-forge-commit"), "w") as f:
            f.write(current)
    except Exception:
        pass


def reload_session(session_path, retain_tokens, min_events, mode="forge",
                   dry_run=False, verbose=False):
    """Core reload logic shared by swap and forge."""
    old_sid = os.path.basename(session_path).replace(".jsonl", "")
    print(f"[{mode}] Session: {old_sid}")

    events = read_jsonl(session_path)
    print(f"Total events: {len(events)}")

    if not dry_run and len(events) < min_events:
        print(f"Only {len(events)} events (min {min_events}), skipping {mode}")
        return False

    keepable = filter_keepable(events)
    print(f"Keepable events: {len(keepable)}")

    if verbose:
        heavy = [e for e in events if e.get("type") in KEEPABLE_TYPES and is_heavy_event(e)]
        print(f"Heavy events filtered: {len(heavy)} (~{sum(estimate_tokens(e) for e in heavy)} tokens)")

    cut = find_clean_boundary(keepable, retain_tokens)
    retained = keepable[cut:]
    print(f"Retained events: {len(retained)} (cut at index {cut})")

    retained = ensure_tool_primer(retained)
    print(f"After tool primer cleanup: {len(retained)}")

    total_tokens = sum(estimate_tokens(e) for e in retained)
    print(f"Estimated retained tokens: ~{total_tokens}")

    if dry_run:
        print(f"\n=== DRY RUN ({mode}) - would keep: ===")
        type_counts = {}
        for e in retained:
            t = e.get("type", "?")
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in sorted(type_counts.items()):
            print(f"  {t}: {c}")
        return True

    new_sid = str(uuid.uuid4())
    print(f"New session ID: {new_sid}")

    rewritten = rewrite_session_chain(retained, new_sid)

    new_path = os.path.join(PROJECT_DIR, f"{new_sid}.jsonl")
    write_jsonl(new_path, rewritten)
    print(f"Wrote new transcript: {new_path}")

    archive_old(session_path)
    mark_last_good(new_sid)
    mark_forge_commit()

    print(f"\n{mode.capitalize()} complete! Resume with:")
    print(f"  claude --resume {new_sid}")

    return new_sid


def swap(session_path=None, dry_run=False, verbose=False):
    if session_path is None:
        session_path = find_active_session()
        if not session_path:
            print("No active session found")
            return False
    return reload_session(session_path, SWAP_RETAIN_TOKENS, SWAP_MIN_EVENTS,
                          mode="swap", dry_run=dry_run, verbose=verbose)


def forge(session_path=None, dry_run=False, verbose=False):
    if session_path is None:
        session_path = find_active_session()
        if not session_path:
            print("No active session found")
            return False
    result = reload_session(session_path, FORGE_RETAIN_TOKENS, FORGE_MIN_EVENTS,
                            mode="forge", dry_run=dry_run, verbose=verbose)
    if result and not dry_run:
        reset_swap_count()
    return result


def auto(dry_run=False, verbose=False):
    """Decide swap vs forge vs skip based on current state."""
    session_path = find_active_session()
    if not session_path:
        print("[auto] No active session found")
        return False

    stats = get_transcript_stats(session_path)
    tokens = stats["estimated_tokens"]
    events = stats["total_events"]
    print(f"[auto] Transcript: {events} events, ~{tokens} tokens")

    code_changed = check_code_changes()
    if code_changed:
        print("[auto] Config files changed → forge")
        result = reload_session(session_path, FORGE_RETAIN_TOKENS, 0,
                                mode="forge", dry_run=dry_run, verbose=verbose)
        if result and not dry_run:
            reset_swap_count()
        return result

    if tokens >= SWAP_TRIGGER_TOKENS:
        swap_count = get_swap_count()
        if swap_count >= SWAP_BEFORE_FORGE:
            print(f"[auto] Tokens ({tokens}) >= {SWAP_TRIGGER_TOKENS}, swaps ({swap_count}) >= {SWAP_BEFORE_FORGE} → forge")
            result = reload_session(session_path, FORGE_RETAIN_TOKENS, 0,
                                    mode="forge", dry_run=dry_run, verbose=verbose)
            if result and not dry_run:
                reset_swap_count()
            return result
        print(f"[auto] Tokens ({tokens}) >= {SWAP_TRIGGER_TOKENS}, swap #{swap_count + 1} → swap")
        result = reload_session(session_path, SWAP_RETAIN_TOKENS, 0,
                                mode="swap", dry_run=dry_run, verbose=verbose)
        if result and not dry_run:
            increment_swap_count()
        return result

    print(f"[auto] No action needed (tokens={tokens}, threshold={SWAP_TRIGGER_TOKENS})")
    return False


def status():
    """Print current transcript stats."""
    session_path = find_active_session()
    if not session_path:
        print("No active session found")
        return
    stats = get_transcript_stats(session_path)
    sid = os.path.basename(stats["path"]).replace(".jsonl", "")
    print(f"Session:  {sid[:8]}...")
    print(f"Events:   {stats['total_events']} total, {stats['keepable_events']} keepable")
    print(f"Tokens:   ~{stats['estimated_tokens']}")
    print(f"Swap at:  {SWAP_TRIGGER_TOKENS}")
    pct = int(stats["estimated_tokens"] / SWAP_TRIGGER_TOKENS * 100)
    print(f"Pressure: {pct}%")
    sc = get_swap_count()
    print(f"Swaps:    {sc}/{SWAP_BEFORE_FORGE} (forge at {SWAP_BEFORE_FORGE})")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    verbose = "--verbose" in args or "-v" in args
    mode_swap = "--swap" in args
    mode_auto = "--auto" in args
    mode_status = "--status" in args
    session_id = None

    for arg in args:
        if not arg.startswith("-"):
            session_id = arg

    session_path = None
    if session_id:
        for d in CANDIDATE_PROJECT_DIRS:
            candidate = os.path.join(d, f"{session_id}.jsonl")
            if os.path.exists(candidate):
                session_path = candidate
                PROJECT_DIR = d
                ARCHIVE_DIR = os.path.join(d, "archive")
                break
        if not session_path:
            print(f"Session not found in any project dir: {session_id}")
            sys.exit(1)

    if mode_status:
        status()
    elif mode_auto:
        result = auto(dry_run=dry_run, verbose=verbose)
        if not result:
            sys.exit(1)
    elif mode_swap:
        result = swap(session_path, dry_run=dry_run, verbose=verbose)
        if not result:
            sys.exit(1)
    else:
        result = forge(session_path, dry_run=dry_run, verbose=verbose)
        if not result:
            sys.exit(1)
