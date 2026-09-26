"""Ties a Claude Code session to the caddie project it's currently
working on, and keeps that project's accumulated cost current.

`/caddie:ask` and `/caddie:explore` call `caddie track-start` once, as
soon as they know which project directory they're working in. That
writes a small marker (`~/.caddie/state/session-<session_id>.json`)
naming the project - the only thing either skill does that's related
to cost tracking. Everything else - reading token usage, pricing it,
updating the project's running total, copying the session transcript,
and pushing a rendered `costs` cell into the live notebook - happens in
`caddie track-update`, wired up as a `Stop` hook (fires once per
top-level Claude Code turn, which is exactly one `/ask` episode or one
`/explore` instruction). None of it depends on the agent remembering to
do anything, by design - see `.specs/`'s cost-tracking plan.
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from caddie.cost import transcript as transcript_mod
from caddie.cost.pricing import TokenUsage, price
from caddie.notebook.state import ProjectState, load_state, save_state

STATE_DIR = Path.home() / ".caddie" / "state"
TRANSCRIPTS_DIRNAME = ".transcripts"


def marker_path(session_id: str) -> Path:
    return STATE_DIR / f"session-{session_id}.json"


def write_marker(session_id: str, project_dir: Path) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker_path(session_id).write_text(json.dumps({"project_dir": str(project_dir)}))


def read_marker(session_id: str) -> Path | None:
    path = marker_path(session_id)
    if not path.is_file():
        return None
    raw = json.loads(path.read_text())
    project_dir = Path(raw["project_dir"])
    return project_dir if project_dir.is_dir() else None


@dataclass
class UpdateResult:
    state: ProjectState
    changed: bool


def _empty_costs() -> dict:
    return {"total_usd": 0.0, "unpriced_tokens": {}, "by_model": {}, "sessions": {}}


def apply_usage(costs: dict, session_id: str, by_model: dict[str, TokenUsage]) -> dict:
    """Fold newly-seen token usage into a project's `costs` sidecar
    block, returning the updated dict. Pure function of its inputs, so
    it's covered by tests without touching disk or a transcript."""
    costs = json.loads(json.dumps(costs)) if costs else _empty_costs()
    for key in ("total_usd", "unpriced_tokens", "by_model", "sessions"):
        costs.setdefault(key, _empty_costs()[key])

    session_entry = costs["sessions"].setdefault(session_id, {"usd": 0.0})

    for model, usage in by_model.items():
        priced = price(model, usage)
        model_entry = costs["by_model"].setdefault(model, {"tokens": TokenUsage().as_dict(), "usd": 0.0})
        model_tokens = TokenUsage.from_dict(model_entry["tokens"]) + usage
        model_entry["tokens"] = model_tokens.as_dict()

        if priced.usd is None:
            unpriced = TokenUsage.from_dict(costs["unpriced_tokens"].get(model, {})) + usage
            costs["unpriced_tokens"][model] = unpriced.as_dict()
            continue

        model_entry["usd"] += priced.usd
        costs["total_usd"] += priced.usd
        session_entry["usd"] += priced.usd

    return costs


def copy_transcripts(project_dir: Path, session_id: str, transcript_path: Path) -> None:
    """Full, unfiltered copy of this session's transcript (main file +
    any subagent files) into the project directory, overwriting on each
    call. Hidden directory, same treatment as `.caddie_project.json` -
    this is raw session data kept alongside the notebook, not notebook
    content."""
    dest_dir = project_dir / TRANSCRIPTS_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)

    if transcript_path.is_file():
        shutil.copy2(transcript_path, dest_dir / f"{session_id}.jsonl")

    sub_dir = transcript_mod.subagent_dir(transcript_path)
    if sub_dir.is_dir():
        dest_sub_dir = dest_dir / session_id / "subagents"
        dest_sub_dir.mkdir(parents=True, exist_ok=True)
        for sub_path in sub_dir.glob("agent-*.jsonl"):
            shutil.copy2(sub_path, dest_sub_dir / sub_path.name)


def update_project(project_dir: Path, session_id: str, transcript_path: Path) -> UpdateResult:
    """Read new usage since this (project, session) pair's last known
    cursor, price it, fold it into the sidecar, and copy the transcript
    - everything `track-update` needs except pushing the rendered cell
    into a live kernel (kept separate so a missing/unpaired kernel
    doesn't block the accounting)."""
    state = load_state(project_dir) or ProjectState(connector="", connector_settings={})
    costs = state.costs or _empty_costs()
    for key in ("total_usd", "unpriced_tokens", "by_model", "sessions"):
        costs.setdefault(key, _empty_costs()[key])

    session_entry = costs["sessions"].get(session_id, {})
    since_line = session_entry.get("cursor_line", 0)
    seen_subagents = session_entry.get("seen_subagents", [])

    result = transcript_mod.episode_usage(transcript_path, since_line, seen_subagents)
    changed = bool(result.by_model)

    costs = apply_usage(costs, session_id, result.by_model)
    costs["sessions"][session_id]["cursor_line"] = result.new_cursor_line
    costs["sessions"][session_id]["seen_subagents"] = result.new_seen_subagents

    state.costs = costs
    save_state(project_dir, state)
    copy_transcripts(project_dir, session_id, transcript_path)

    return UpdateResult(state=state, changed=changed)


def render_costs_markdown(costs: dict) -> str:
    total = costs.get("total_usd", 0.0)
    lines = [f"**Total cost so far: ${total:,.4f}**", ""]

    by_model = costs.get("by_model", {})
    if by_model:
        lines.append("| model | tokens | cost |")
        lines.append("| --- | ---: | ---: |")
        for model, entry in sorted(by_model.items()):
            tokens = TokenUsage.from_dict(entry["tokens"])
            total_tokens = (
                tokens.input_tokens
                + tokens.output_tokens
                + tokens.cache_creation_5m_tokens
                + tokens.cache_creation_1h_tokens
                + tokens.cache_read_tokens
            )
            lines.append(f"| {model} | {total_tokens:,} | ${entry['usd']:,.4f} |")
        lines.append("")

    unpriced = costs.get("unpriced_tokens", {})
    if unpriced:
        lines.append(
            "_Unpriced usage (model not in caddie's pricing table - update "
            "`caddie.cost.pricing` to include it):_"
        )
        for model, tokens_raw in sorted(unpriced.items()):
            tokens = TokenUsage.from_dict(tokens_raw)
            lines.append(f"- {model}: {tokens.input_tokens + tokens.output_tokens:,} tokens")
        lines.append("")

    lines.append(f"_Tracked across {len(costs.get('sessions', {}))} Claude Code session(s)._")
    return "\n".join(lines)


def costs_cell_code(costs: dict) -> str:
    markdown = render_costs_markdown(costs)
    return f"mo.md({markdown!r})"
