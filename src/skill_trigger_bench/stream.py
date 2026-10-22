"""Parse `claude -p --output-format stream-json --verbose` transcripts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


@dataclass
class Transcript:
    loaded_skills: list[str] | None = None  # from the init event, when present
    skill_calls: list[str] = field(default_factory=list)  # in call order
    tool_calls: list[str] = field(default_factory=list)
    result: str | None = None
    finished: bool = False  # a final "result" event was seen
    subtype: str | None = None
    is_error: bool = False
    cost_usd: float | None = None
    bad_lines: int = 0

    def activated(self, skill: str) -> bool:
        return any(skill_matches(call, skill) for call in self.skill_calls)

    def first_skill(self) -> str | None:
        return self.skill_calls[0] if self.skill_calls else None


def skill_matches(called: str, skill: str) -> bool:
    """'pdf' matches 'pdf', 'plugin:pdf' and '/pdf'."""
    called = called.strip().lstrip("/")
    return called == skill or called.rsplit(":", 1)[-1] == skill


def _skill_name_from_input(inp) -> str | None:
    if not isinstance(inp, dict):
        return None
    for key in ("skill", "name", "command", "skill_name"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().split()[0]
    return None


def _content_blocks(event: dict):
    msg = event.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            return content
    return []


def parse_events(events) -> Transcript:
    t = Transcript()
    for ev in events:
        if not isinstance(ev, dict):
            t.bad_lines += 1
            continue
        typ = ev.get("type")
        if typ == "system" and ev.get("subtype") == "init":
            sk = ev.get("skills")
            if isinstance(sk, list):
                t.loaded_skills = [s if isinstance(s, str) else str(s.get("name", "")) for s in sk]
        elif typ == "assistant":
            for block in _content_blocks(ev):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name", "")
                    t.tool_calls.append(name)
                    if name == "Skill":
                        s = _skill_name_from_input(block.get("input"))
                        if s:
                            t.skill_calls.append(s)
        elif typ == "result":
            t.finished = True
            t.subtype = ev.get("subtype")
            t.result = ev.get("result") if isinstance(ev.get("result"), str) else None
            # running out of turns is expected here (we cap turns low); anything else is a real error
            if t.subtype == "error_max_turns":
                t.is_error = False
            else:
                t.is_error = bool(ev.get("is_error")) or t.subtype not in (None, "success")
            cost = ev.get("total_cost_usd", ev.get("cost_usd"))
            if isinstance(cost, (int, float)):
                t.cost_usd = float(cost)
    return t


def parse_lines(lines) -> Transcript:
    events = []
    bad = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            bad += 1
    t = parse_events(events)
    t.bad_lines += bad
    return t


def parse_text(text: str) -> Transcript:
    return parse_lines(text.splitlines())


# --- Codex CLI -------------------------------------------------------------------------
# `codex exec --json` event schema: openai/codex codex-rs/exec/src/exec_events.rs and
# https://learn.chatgpt.com/docs/non-interactive-mode. Top-level types are thread.started,
# turn.started, turn.completed, turn.failed, item.started, item.updated, item.completed and
# error. Item types are agent_message, reasoning, command_execution, file_change,
# mcp_tool_call, collab_tool_call, web_search, todo_list and error. There is no skill item,
# so activation is inferred from a shell command that reads <skill>/SKILL.md (Codex docs:
# "When Codex selects a skill, it still reads the full SKILL.md instructions").

_SKILL_MD = re.compile(r"([^\s/\\'\"]+)[/\\]SKILL\.md\b")


def codex_skill_reads(command: str) -> list[str]:
    """Skill folder names whose SKILL.md this command touches (heuristic)."""
    return _SKILL_MD.findall(command or "")


def parse_codex_events(events, names: dict[str, str] | None = None) -> Transcript:
    """`names` maps installed skill folder -> frontmatter name."""
    names = names or {}
    t = Transcript()
    seen: set[str] = set()
    for ev in events:
        if not isinstance(ev, dict):
            t.bad_lines += 1
            continue
        typ = ev.get("type")
        if typ in ("item.started", "item.completed"):
            item = ev.get("item")
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            iid = item.get("id")
            if itype == "command_execution":
                if typ == "item.started" or iid not in seen:
                    t.tool_calls.append("command_execution")
                for folder in codex_skill_reads(item.get("command", "")):
                    skill = names.get(folder, folder)
                    if (iid, skill) not in seen:
                        t.skill_calls.append(skill)
                        seen.add((iid, skill))
                seen.add(iid)
            elif itype == "agent_message" and typ == "item.completed":
                t.result = item.get("text") if isinstance(item.get("text"), str) else t.result
            elif itype == "error" and typ == "item.completed":
                # non-fatal warnings are reported as error items; only turn.failed/error end a run
                pass
        elif typ == "turn.completed":
            t.finished = True
            t.subtype = "success"
        elif typ in ("turn.failed", "error"):
            t.finished = True
            t.is_error = True
            t.subtype = typ
            err = ev.get("error") if typ == "turn.failed" else ev
            if isinstance(err, dict) and isinstance(err.get("message"), str):
                t.result = err["message"]
    return t


def parse_codex_text(text: str, names: dict[str, str] | None = None) -> Transcript:
    events, bad = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            bad += 1
    t = parse_codex_events(events, names)
    t.bad_lines += bad
    return t


# --- Gemini CLI ------------------------------------------------------------------------
# `gemini -p ... --output-format stream-json` emits one JSON event per line. Schema from
# google-gemini/gemini-cli packages/core/src/output/types.ts:
#   init        {session_id, model}
#   message     {role: user|assistant, content, delta?}
#   tool_use    {tool_name, tool_id, parameters}
#   tool_result {tool_id, status: success|error, output?, error?}
#   error       {severity: warning|error, message}
#   result      {status: success|error, error?, stats?}
# Skills are activated by the `activate_skill` tool with a `name` parameter
# (packages/core/src/tools/activate-skill.ts). The older saved-session format
# (`type: "gemini"` with `toolCalls`) is still accepted as a fallback.
_GEMINI_SKILL_TOOLS = ("activate_skill", "skill", "load_skill", "use_skill")


def _gemini_tool_call(t: Transcript, seen: set, names: dict, cname: str, cid: str, args) -> None:
    t.tool_calls.append(cname)
    if not isinstance(args, dict):
        args = {}
    marks = []
    if cname.lower() in _GEMINI_SKILL_TOOLS:
        s = _skill_name_from_input(args)
        if s:
            marks.append(s)
    cmd = args.get("command") or args.get("file_path") or args.get("absolute_path") or args.get("path") or ""
    marks += _SKILL_MD.findall(str(cmd))
    for s in marks:
        mapped = names.get(s, s)
        if (cid, mapped) not in seen:
            t.skill_calls.append(mapped)
            seen.add((cid, mapped))


def parse_gemini_events(events, names: dict[str, str] | None = None) -> Transcript:
    names = names or {}
    t = Transcript()
    seen: set = set()
    text = ""
    for ev in events:
        if not isinstance(ev, dict):
            t.bad_lines += 1
            continue
        typ = ev.get("type")
        if typ == "tool_use":
            cid = ev.get("tool_id") or str(id(ev))
            _gemini_tool_call(t, seen, names, ev.get("tool_name", ""), cid, ev.get("parameters"))
            text = ""
        elif typ == "message":
            if ev.get("role") == "assistant" and isinstance(ev.get("content"), str):
                text = text + ev["content"] if ev.get("delta") else ev["content"]
                t.result = text
        elif typ == "error":
            if ev.get("severity") == "warning":
                continue
            t.finished = True
            t.is_error = True
            err = ev.get("error")
            if isinstance(err, dict):  # session format
                code = err.get("code")
                msg = err.get("message", "")
                t.result = f"{code}: {msg}" if code is not None else str(msg or err)
            else:
                t.result = str(ev.get("message") or err or "Unknown error")
        elif typ == "gemini":  # saved-session fallback
            t.finished = True
            for call in ev.get("toolCalls") or []:
                if isinstance(call, dict):
                    cid = call.get("id") or str(id(call))
                    _gemini_tool_call(t, seen, names, call.get("name", ""), cid, call.get("args"))
            content = ev.get("content")
            if isinstance(content, str):
                t.result = content
            elif isinstance(content, list):
                texts = [
                    b.get("text") for b in content if isinstance(b, dict) and b.get("text") and not b.get("thought")
                ]
                if texts:
                    t.result = texts[-1]
        elif typ == "result":
            t.finished = True
            if ev.get("status") == "error":
                t.is_error = True
                err = ev.get("error")
                if isinstance(err, dict):
                    t.result = str(err.get("message") or err.get("type") or "Error")
                else:
                    t.result = str(err or "Error")
    return t


def parse_gemini_text(text: str, names: dict[str, str] | None = None) -> Transcript:
    events, bad = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            bad += 1
    t = parse_gemini_events(events, names)
    t.bad_lines += bad
    return t
