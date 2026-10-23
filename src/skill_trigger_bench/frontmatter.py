"""A small YAML-subset parser, enough for SKILL.md frontmatter and prompt files.

Uses PyYAML when it is installed. The fallback handles what skill files use in
practice: ``key: value``, quoted strings, ``>``/``|`` block scalars, nested maps
by indentation, and ``- item`` lists. It is not a general YAML parser.
"""

from __future__ import annotations

import re


class FrontmatterError(ValueError):
    pass


def split_frontmatter(text: str) -> tuple[str | None, str, int]:
    """Return (frontmatter_text, body, body_start_line). Frontmatter is None if absent."""
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]), i + 2
    raise FrontmatterError("frontmatter opened with '---' but never closed")


def load_yaml(text: str):
    try:
        import yaml  # type: ignore
    except ImportError:
        return parse_simple_yaml(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:  # pragma: no cover - depends on PyYAML
        raise FrontmatterError(str(e)) from e


def _scalar(raw: str):
    s = raw.strip()
    if not s:
        return ""
    if (s[0] == s[-1]) and s[0] in "\"'" and len(s) >= 2:
        inner = s[1:-1]
        if s[0] == '"':
            return inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        return inner.replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(p) for p in s[1:-1].split(",") if p.strip()]
    # strip trailing comments for plain scalars
    s = re.sub(r"\s+#.*$", "", s)
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_simple_yaml(text: str):
    lines = [ln.rstrip() for ln in text.replace("\t", "    ").splitlines()]
    value, _ = _parse_block(lines, 0, 0)
    return value


def _skip_blank(lines, i):
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return i


def _parse_block(lines, i, indent):
    i = _skip_blank(lines, i)
    if i >= len(lines):
        return None, i
    if lines[i].lstrip().startswith("- ") or lines[i].strip() == "-":
        return _parse_list(lines, i, _indent(lines[i]))
    return _parse_map(lines, i, _indent(lines[i]))


def _block_scalar(lines, i, parent_indent, style):
    buf = []
    block_indent = None
    while i < len(lines):
        ln = lines[i]
        if ln.strip() and _indent(ln) <= parent_indent:
            break
        if ln.strip() and block_indent is None:
            block_indent = _indent(ln)
        buf.append(ln[block_indent:] if block_indent and ln.strip() else ln.strip())
        i += 1
    while buf and not buf[-1]:
        buf.pop()
    if style.startswith("|"):
        out = "\n".join(buf)
    else:
        paras, cur = [], []
        for b in buf:
            if b:
                cur.append(b.strip())
            else:
                paras.append(" ".join(cur))
                cur = []
        paras.append(" ".join(cur))
        out = "\n".join(paras)
    return out, i


def _value_after_key(lines, i, indent, rest):
    rest = rest.strip()
    if rest and rest[0] in "|>" and re.fullmatch(r"[|>][+-]?\d*", rest):
        return _block_scalar(lines, i + 1, indent, rest)
    if rest:
        # plain multi-line scalar continuation
        j = i + 1
        parts = [rest]
        if rest[0] not in "\"'[":
            while j < len(lines) and lines[j].strip() and _indent(lines[j]) > indent:
                if re.match(r"^\s*[\w.-]+:\s", lines[j] + " ") or lines[j].lstrip().startswith("- "):
                    break
                parts.append(lines[j].strip())
                j += 1
            if re.search(r":(\s|$)", re.sub(r"\s+#.*$", "", " ".join(parts))):
                # Real YAML parsers (PyYAML, and the one Claude Code uses) reject this,
                # so the skill would not load. Say so instead of accepting it.
                raise FrontmatterError(
                    f"line {i + 1}: a ': ' inside an unquoted value is not valid YAML, put the value in quotes"
                )
        return _scalar(" ".join(parts)), j
    j = _skip_blank(lines, i + 1)
    if j < len(lines) and _indent(lines[j]) > indent:
        return _parse_block(lines, j, _indent(lines[j]))
    if j < len(lines) and _indent(lines[j]) == indent and lines[j].lstrip().startswith("- "):
        return _parse_list(lines, j, indent)
    return None, i + 1


_KEY = re.compile(r"^(\s*)(\"[^\"]*\"|'[^']*'|[^:#\s][^:]*?)\s*:(?:\s+(.*)|$)")


def _parse_map(lines, i, indent):
    out = {}
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines) or _indent(lines[i]) < indent:
            return out, i
        if _indent(lines[i]) > indent:
            raise FrontmatterError(f"unexpected indentation on line {i + 1}: {lines[i].strip()!r}")
        m = _KEY.match(lines[i])
        if not m:
            raise FrontmatterError(f"cannot parse line {i + 1}: {lines[i].strip()!r}")
        key = m.group(2).strip("\"'")
        out[key], i = _value_after_key(lines, i, indent, m.group(3) or "")


def _parse_list(lines, i, indent):
    out = []
    while True:
        i = _skip_blank(lines, i)
        if i >= len(lines) or _indent(lines[i]) != indent or not lines[i].lstrip().startswith("-"):
            return out, i
        rest = lines[i].lstrip()[1:].strip()
        if not rest:
            val, i = _parse_block(lines, i + 1, indent + 1)
            out.append(val)
        elif _KEY.match(" " * (indent + 2) + rest) and rest[0] not in "\"'":
            # inline map item: "- key: value" with more keys indented below
            sub = [" " * (indent + 2) + rest]
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or _indent(lines[j]) > indent):
                sub.append(lines[j])
                j += 1
            val, _ = _parse_map(sub, 0, indent + 2)
            out.append(val)
            i = j
        else:
            out.append(_scalar(rest))
            i += 1
