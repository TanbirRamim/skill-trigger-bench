"""Reproduce the numbers in docs/state-of-skills.md.

Usage: python scripts/state_of_skills.py <dir with shallow clones>

Each clone is expected at <dir>/<owner>_<repo>. Runs `stb lint --format json`
on every pack and on the combined installs, and prints JSON to stdout.
"""
import collections
import os
import json
import subprocess
import sys
from pathlib import Path

# Ordered by GitHub stars at the time of the run.
REPOS = [
    "obra/superpowers",
    "anthropics/skills",
    "ComposioHQ/awesome-claude-skills",
    "alirezarezvani/claude-skills",
    "nidhinjs/prompt-master",
    "Jeffallan/claude-skills",
    "SnailSploit/Claude-Red",
    "SawyerHood/dev-browser",
]
COMPOSIO = "ComposioHQ/awesome-claude-skills"
SRC = Path(__file__).resolve().parent.parent / "src"


def lint(paths):
    out = subprocess.run(
        [sys.executable, "-m", "skill_trigger_bench", "lint", "--format", "json",
         "--no-plugins", *map(str, paths)],
        capture_output=True, text=True, env={"PYTHONPATH": str(SRC), "PATH": os.environ.get("PATH", "")},
    )
    return json.loads(out.stdout)


def summarize(d):
    s = d["stats"]
    rules = collections.Counter(f"{f['rule']}:{f['severity']}" for f in d["findings"])
    names = collections.Counter(k["name"] for k in d["skills"])
    n = s["skills"]
    return {
        "skills": n,
        "description_chars": s["description_chars"],
        "pct_of_budget": round(100 * s["description_chars"] / s["budget"]),
        "errors": s["errors"],
        "warnings": s["warnings"],
        "by_rule": dict(sorted(rules.items())),
        "missing_when_pct": round(100 * rules["description-no-when:warning"] / n) if n else 0,
        "overlapping_pairs": len(s["overlapping_pairs"]),
        "broken_refs": rules["missing-reference:error"],
        "bodies_over_500": rules["body-too-long:warning"],
        "spec_errors": s["errors"] - rules["description-budget:error"]
        - rules["missing-reference:error"] - rules["duplicate-name:error"],
        "budget_message": next((f["message"] for f in d["findings"]
                                if f["rule"] == "description-budget"), ""),
        "name_clashes": sum(1 for c in names.values() if c > 1),
    }


def paths_for(base, repo, part=None):
    root = base / repo.replace("/", "_")
    if repo != COMPOSIO or part is None:
        return [root]
    gen = root / "composio-skills"
    if part == "generated":
        return [gen]
    return sorted(p.parent for p in root.rglob("SKILL.md")
                  if gen not in p.parents and not any(x.startswith(".") for x in p.relative_to(root).parts))


def main():
    base = Path(sys.argv[1])
    res = {"repos": {}, "combined": {}}
    for r in REPOS:
        sha = subprocess.run(["git", "-C", str(base / r.replace("/", "_")), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        if r == COMPOSIO:
            for part in ("top", "generated"):
                res["repos"][f"{r} ({part})"] = {"sha": sha, **summarize(lint(paths_for(base, r, part)))}
        else:
            res["repos"][r] = {"sha": sha, **summarize(lint(paths_for(base, r)))}
    top = lambda k, part: [p for r in REPOS[:k] for p in paths_for(base, r, part)]
    res["combined"]["top2"] = summarize(lint(top(2, None)))
    res["combined"]["top3 (Composio top level)"] = summarize(lint(top(3, "top")))
    res["combined"]["top3 (all)"] = summarize(lint(top(3, None)))
    res["combined"]["top5 (Composio top level)"] = summarize(lint(top(5, "top")))
    res["combined"]["top5 (all)"] = summarize(lint(top(5, None)))
    res["combined"]["all8"] = summarize(lint(top(8, None)))
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
