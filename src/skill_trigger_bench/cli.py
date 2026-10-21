"""Command line entry point: `stb lint` and `stb eval`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .evaluate import run_eval
from .lint import BODY_MAX_LINES, DEFAULT_BUDGET, DEFAULT_OVERLAP, lint, relpath
from .prompts import PromptFileError, generate, load_prompt_file
from .runners import RUNNERS
from .skills import collect, find_skills

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _github_escape_data(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _github_escape_prop(s: str) -> str:
    return _github_escape_data(s).replace(":", "%3A").replace(",", "%2C")


def cmd_lint(args) -> int:
    skills = collect(args.paths, include_plugins=not args.no_plugins)
    if not skills:
        print("no skills found" + (f" in {', '.join(args.paths)}" if args.paths else ""), file=sys.stderr)
        return EXIT_USAGE if args.paths else EXIT_OK
    findings, stats = lint(skills, budget=args.budget, overlap=args.overlap, max_lines=args.max_lines)
    if args.ignore:
        ignored = set(args.ignore.split(","))
        findings = [f for f in findings if f.rule not in ignored]
        stats["errors"] = sum(1 for f in findings if f.severity == "error")
        stats["warnings"] = sum(1 for f in findings if f.severity == "warning")
    failed = stats["errors"] > 0 or (args.strict and stats["warnings"] > 0)
    if args.format == "json":
        out = {
            "version": __version__,
            "ok": not failed,
            "stats": stats,
            "skills": [{"name": s.name, "source": s.source, "path": str(s.path)} for s in skills],
            "findings": [{k: v for k, v in f.to_dict().items() if args.suggest or k != "suggestion"} for f in findings],
        }
        print(json.dumps(out, indent=2))
    elif args.format == "github":
        for f in findings:
            command = {"error": "error", "warning": "warning"}.get(f.severity, "notice")
            title = _github_escape_prop(f.rule)
            text = f"{f.message}\n{f.suggestion}" if args.suggest and f.suggestion else f.message
            msg = _github_escape_data(text)
            if f.path:
                try:
                    rel = os.path.relpath(f.path)
                except ValueError:  # Windows: path on another drive than the cwd
                    rel = str(f.path)
                print(f"::{command} file={_github_escape_prop(rel)},title={title}::{msg}")
            else:
                print(f"::{command} title={title}::{msg}")
    elif args.format == "sarif":
        rules = [{"id": r} for r in sorted({f.rule for f in findings})]
        results = []
        for f in findings:
            text = f"{f.message}\n{f.suggestion}" if args.suggest and f.suggestion else f.message
            level = {"error": "error", "warning": "warning"}.get(f.severity, "note")
            res = {
                "ruleId": f.rule,
                "level": level,
                "message": {"text": text},
            }
            if f.path:
                try:
                    rel = os.path.relpath(f.path)
                except ValueError:  # Windows: path on another drive than the cwd
                    rel = str(f.path)
                res["locations"] = [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": rel.replace("\\", "/"),
                            }
                        }
                    }
                ]
            results.append(res)
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "stb",
                            "version": __version__,
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }
        print(json.dumps(sarif, indent=2))
    else:
        sources = {}
        for s in skills:
            sources[s.source] = sources.get(s.source, 0) + 1
        src = ", ".join(f"{n} {k}" for k, n in sources.items())
        print(f"{stats['skills']} skills ({src})")
        print(f"description budget: {stats['description_chars']} / ~{stats['budget']} chars")
        print()
        for f in findings:
            print(f"{f.severity:<7} {f.rule:<22} {f.skill}: {f.message}")
            if args.suggest and f.suggestion:
                for line in f.suggestion.splitlines():
                    print(f"  {line}")
            if args.verbose and f.path:
                print(f"{'':30}{relpath(f.path)}")
        if findings:
            print()
        print(f"{stats['errors']} errors, {stats['warnings']} warnings")
    return EXIT_FAIL if failed else EXIT_OK


def cmd_eval(args) -> int:
    targets = find_skills(Path(args.skill))
    if len(targets) != 1:
        print(f"expected one skill at {args.skill}, found {len(targets)}", file=sys.stderr)
        return EXIT_USAGE
    skill = targets[0]
    if skill.error or not skill.description:
        print(f"{skill.name}: {skill.error or 'no description'}; run `stb lint` first", file=sys.stderr)
        return EXIT_USAGE
    neighbours = []
    for p in args.with_skills or []:
        neighbours += find_skills(Path(p))
    if args.prompts:
        try:
            prompts = load_prompt_file(Path(args.prompts))
        except (OSError, ValueError, PromptFileError) as e:
            print(f"cannot read prompts: {e}", file=sys.stderr)
            return EXIT_USAGE
    else:
        prompts = generate(skill, neighbours, n=args.n)
    runner = RUNNERS[args.runner](model=args.model, timeout=args.timeout)
    total = len(prompts.should_trigger) + len(prompts.should_not_trigger)
    if args.dry_run:
        print(
            json.dumps(
                {"should_trigger": prompts.should_trigger, "should_not_trigger": prompts.should_not_trigger}, indent=2
            )
        )
        return EXIT_OK
    if not runner.available():
        print(f"runner '{args.runner}' is not available (is `{args.runner}` on PATH?)", file=sys.stderr)
        return EXIT_USAGE
    if args.max_prompts and total > args.max_prompts:
        print(
            f"{total} prompts is more than --max-prompts {args.max_prompts}; refusing (each one is a model call)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    def progress(i, n, r):
        if args.format == "text":
            mark = "ERR" if r.triggered is None else ("yes" if r.triggered else "no ")
            want = "should" if r.expected else "should not"
            print(f"[{i}/{n}] {mark}  ({want}) {r.prompt[:70]}", file=sys.stderr)

    report = run_eval(skill, neighbours, prompts, runner, progress)
    ok = report.passed(args.min_trigger, args.max_false)
    if getattr(args, "html", None):
        from .report import generate_html_report

        html_doc = generate_html_report(
            report,
            min_trigger=args.min_trigger,
            max_false=args.max_false,
            model=args.model,
        )
        Path(args.html).write_text(html_doc, encoding="utf-8")
    if args.format == "json":
        d = report.to_dict()
        d.update(ok=ok, generated_prompts=prompts.generated, min_trigger=args.min_trigger, max_false=args.max_false)
        print(json.dumps(d, indent=2))
    else:
        print(f"\n{skill.name} via {report.runner}" + (" (generated prompts)" if prompts.generated else ""))
        print(f"trigger rate:       {_pct(report.trigger_rate)}  (want >= {_pct(args.min_trigger)})")
        print(f"false-trigger rate: {_pct(report.false_trigger_rate)}  (want <= {_pct(args.max_false)})")
        if report.errors:
            print(f"failed runs: {report.errors}")
        if report.skill_not_loaded:
            print("warning: the agent did not list this skill as loaded; check its frontmatter")
        if report.cost_usd:
            print(f"cost: ${report.cost_usd:.4f}")
        for r in report.results:
            if r.triggered is not None and r.triggered != r.expected:
                kind = "missed" if r.expected else "false trigger"
                print(f"  {kind}: {r.prompt}" + (f"  (called: {', '.join(r.skill_calls)})" if r.skill_calls else ""))
        print("PASS" if ok else "FAIL")
    return EXIT_OK if ok else EXIT_FAIL


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stb", description="Check whether your Agent Skills actually trigger.")
    p.add_argument("--version", action="version", version=f"stb {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    lp = sub.add_parser("lint", help="static checks across a set of skills (offline)")
    lp.add_argument(
        "paths",
        nargs="*",
        help="skill folders or dirs of skills (default: ~/.claude/skills, .claude/skills, installed plugins)",
    )
    lp.add_argument("--format", choices=["text", "json", "github", "sarif"], default="text")
    lp.add_argument(
        "--budget", type=int, default=DEFAULT_BUDGET, help="description budget in chars (default %(default)s)"
    )
    lp.add_argument(
        "--overlap",
        type=float,
        default=DEFAULT_OVERLAP,
        help="cosine threshold for trigger overlap (default %(default)s)",
    )
    lp.add_argument(
        "--max-lines", type=int, default=BODY_MAX_LINES, help="SKILL.md body line limit (default %(default)s)"
    )
    lp.add_argument("--ignore", help="comma-separated rule names to skip")
    lp.add_argument("--suggest", action="store_true", help="show suggested fixes (does not modify files)")
    lp.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    lp.add_argument("--no-plugins", action="store_true", help="skip installed plugin skills")
    lp.add_argument("-v", "--verbose", action="store_true", help="show file paths")
    lp.set_defaults(func=cmd_lint)

    ep = sub.add_parser("eval", help="run prompts through an agent and measure activation (calls a model)")
    ep.add_argument("skill", help="path to the skill folder")
    ep.add_argument("--prompts", help="YAML or JSON file with should_trigger / should_not_trigger lists")
    ep.add_argument(
        "--with", dest="with_skills", action="append", help="also install these skills in the sandbox (repeatable)"
    )
    ep.add_argument("--agent", "--runner", dest="runner", choices=sorted(RUNNERS), default="claude")
    ep.add_argument("--model", help="model passed to the runner")
    ep.add_argument("-n", type=int, default=5, help="generated prompts per side (default %(default)s)")
    ep.add_argument("--min-trigger", type=float, default=0.8)
    ep.add_argument("--max-false", type=float, default=0.2)
    ep.add_argument("--max-prompts", type=int, default=40, help="safety cap on model calls (0 = no cap)")
    ep.add_argument("--timeout", type=int, default=180)
    ep.add_argument("--dry-run", action="store_true", help="print the prompts and exit")
    ep.add_argument("--html", help="write self-contained HTML report to PATH")
    ep.add_argument("--format", choices=["text", "json"], default="text")
    ep.set_defaults(func=cmd_eval)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
