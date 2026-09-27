"""Reads token usage out of Claude Code's own session transcripts.

A session's transcript is a JSONL file at
`~/.claude/projects/<slug>/<session_id>.jsonl` - the `transcript_path`
a `Stop` hook receives on stdin points straight at it. Every
`type: "assistant"` line carries a `message.usage` block (input/output/
cache tokens), always present, unlike the rare `cost-state` entries
Claude Code occasionally appends with an already-computed `costUSD`
(too sparse to build a deterministic hook around - see `pricing.py`'s
module docstring).

Subagent calls (exactly how `/caddie:ask` invokes `lead-analyst` and
`data-analyst`, via the Agent tool) never appear inline in the parent
transcript - they land in sibling files at
`<session_dir>/subagents/agent-*.jsonl`, one per invocation. Any cost
accounting for a caddie episode has to add these in too, or it only
counts the orchestrating turn and misses most of the actual cost.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from caddie.cost.pricing import TokenUsage


def _usage_from_message(message: dict) -> tuple[str, TokenUsage] | None:
    model = message.get("model")
    usage = message.get("usage")
    if not model or not isinstance(usage, dict):
        return None
    if model == "<synthetic>":
        # Claude Code's own placeholder for a locally-generated assistant
        # message (no real API call happened) - always zero tokens, and
        # not a model `pricing.py` could ever price.
        return None

    cache_creation = usage.get("cache_creation") or {}
    return model, TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_creation_5m_tokens=cache_creation.get("ephemeral_5m_input_tokens", 0),
        cache_creation_1h_tokens=cache_creation.get("ephemeral_1h_input_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
    )


def _iter_assistant_usage(lines: list[str]):
    """Yields (model, usage) once per distinct API response.

    A single API response that spans multiple content blocks (e.g. a
    thinking/text block plus a tool-use block) is logged as one
    `type: "assistant"` JSONL line per block, all sharing the same
    `message.id` - and Claude Code copies the *same* `usage` object
    onto every one of those lines. Summing them all would count that
    response's tokens once per block instead of once total, so this
    dedupes by `message.id` (falling back to identity, i.e. always
    counted, for the rare entry missing one) before yielding."""
    seen_message_ids: set[str] = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        message_id = message.get("id")
        if message_id is not None:
            if message_id in seen_message_ids:
                continue
            seen_message_ids.add(message_id)
        result = _usage_from_message(message)
        if result is not None:
            yield result


def usage_by_model_in_lines(lines: list[str]) -> dict[str, TokenUsage]:
    totals: dict[str, TokenUsage] = {}
    for model, usage in _iter_assistant_usage(lines):
        totals[model] = totals.get(model, TokenUsage()) + usage
    return totals


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(errors="replace").splitlines()


def subagent_dir(main_transcript_path: Path) -> Path:
    return main_transcript_path.parent / main_transcript_path.stem / "subagents"


def subagent_transcripts(main_transcript_path: Path) -> list[Path]:
    """Sibling per-subagent transcript files for this session, if any.

    Claude Code nests these under a directory named for the session id
    (`<session_dir>/<session_id>/subagents/agent-*.jsonl`), alongside
    the main `<session_id>.jsonl` file itself."""
    d = subagent_dir(main_transcript_path)
    if not d.is_dir():
        return []
    return sorted(d.glob("agent-*.jsonl"))


@dataclass
class EpisodeUsage:
    by_model: dict[str, TokenUsage]
    new_cursor_line: int
    new_seen_subagents: list[str]


def episode_usage(
    transcript_path: Path,
    since_line: int,
    seen_subagents: list[str],
) -> EpisodeUsage:
    """Token usage attributable to whatever happened since the last time
    this was called for this (session, project) pair: new lines in the
    main transcript past `since_line`, plus any subagent transcript file
    not already in `seen_subagents` (a subagent's file is only ever
    fully written once its call completes, so any file not seen before
    is safe to count in full)."""
    lines = read_lines(transcript_path)
    new_lines = lines[since_line:]

    totals = usage_by_model_in_lines(new_lines)

    all_subagents = subagent_transcripts(transcript_path)
    seen = set(seen_subagents)
    new_seen = list(seen_subagents)
    for sub_path in all_subagents:
        name = sub_path.name
        if name in seen:
            continue
        sub_totals = usage_by_model_in_lines(read_lines(sub_path))
        for model, usage in sub_totals.items():
            totals[model] = totals.get(model, TokenUsage()) + usage
        new_seen.append(name)

    return EpisodeUsage(
        by_model=totals,
        new_cursor_line=len(lines),
        new_seen_subagents=new_seen,
    )
