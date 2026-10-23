import contextlib
import io
import json
from unittest.mock import patch

from skill_trigger_bench.cli import main
from skill_trigger_bench.lint import Finding

from .helpers import SkillDirCase

GOOD = "Summarize CSV files with column types. Use when the user asks what is in a CSV file."


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(SkillDirCase):
    def test_lint_clean_exit_zero(self):
        self.make_skill("csv-summary", "csv-summary", GOOD)
        code, out, _ = run(["lint", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn("0 errors, 0 warnings", out)

    def test_lint_error_exit_one(self):
        self.make_skill("x", extra="license: MIT")
        self.assertEqual(run(["lint", str(self.root)])[0], 1)

    def test_strict_fails_on_warnings(self):
        self.make_skill("x", "x", "Converts PDF documents into clean Markdown text output.")
        self.assertEqual(run(["lint", str(self.root)])[0], 0)
        self.assertEqual(run(["lint", "--strict", str(self.root)])[0], 1)

    def test_ignore_rule(self):
        self.make_skill("x", "x", "Converts PDF documents into clean Markdown text output.")
        code, out, _ = run(["lint", "--strict", "--ignore", "description-no-when", str(self.root)])
        self.assertEqual(code, 0)

    def test_json_output(self):
        self.make_skill("csv-summary", "csv-summary", GOOD)
        code, out, _ = run(["lint", "--format", "json", str(self.root)])
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["skills"][0]["name"], "csv-summary")
        self.assertEqual(data["findings"], [])

    def test_suggest_text_is_opt_in_and_beneath_finding(self):
        self.make_skill("folder", "other-name", GOOD)
        _, plain, _ = run(["lint", str(self.root)])
        _, suggested, _ = run(["lint", "--suggest", str(self.root)])
        self.assertNotIn("+ name:", plain)
        lines = suggested.splitlines()
        index = next(i for i, line in enumerate(lines) if "name-dir-mismatch" in line)
        self.assertEqual(lines[index + 1 : index + 3], ['  - name: "other-name"', '  + name: "folder"'])
        self.assertEqual("\n".join(line for line in lines if not line.startswith(("  -", "  +"))) + "\n", plain)

    def test_suggest_json_preserves_existing_fields(self):
        self.make_skill("folder", "My_Skill", "PDF conversion with tables preserved.")
        self.make_skill("missing", extra="license: MIT")
        plain_code, plain, _ = run(["lint", "--format", "json", str(self.root)])
        code, suggested, _ = run(["lint", "--format", "json", "--suggest", str(self.root)])
        baseline, data = json.loads(plain), json.loads(suggested)
        self.assertEqual(code, plain_code)
        self.assertEqual(set(baseline), {"version", "ok", "stats", "skills", "findings"})
        for original, finding in zip(baseline["findings"], data["findings"], strict=True):
            self.assertEqual(set(original), {"rule", "severity", "skill", "message", "path"})
            if finding["rule"] in {"name-format", "name-dir-mismatch", "description-no-when"}:
                self.assertTrue(finding.pop("suggestion"))
            self.assertEqual(finding, original)
        self.assertEqual(data, baseline)

    def test_suggest_json_keeps_optional_existing_fields(self):
        self.make_skill("x", "x", GOOD)
        finding = Finding("trigger-overlap", "warning", "x", "message", other="y", suggestion="+ draft")
        stats = {"errors": 0, "warnings": 1}
        with patch("skill_trigger_bench.cli.lint", return_value=([finding], stats)):
            for options in ([], ["--suggest"]):
                _, out, _ = run(["lint", str(self.root), "--format", "json"] + options)
                expected = {
                    "rule": "trigger-overlap",
                    "severity": "warning",
                    "skill": "x",
                    "message": "message",
                    "other": "y",
                }
                if options:
                    expected["suggestion"] = "+ draft"
                self.assertEqual(json.loads(out)["findings"], [expected])

    def test_suggest_cli_never_modifies_skill_files(self):
        self.make_skill("folder", "My_Skill", "Works wonders for everyone.")
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("SKILL.md")}
        for fmt in ("text", "json", "github", "sarif"):
            run(["lint", str(self.root), "--suggest", "--format", fmt])
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("SKILL.md")})

    def test_suggest_preserves_exit_counts_ignore_strict_and_github(self):
        cases = [
            (GOOD, "x", [], 0),
            (GOOD, "My_Skill", [], 1),
            ("PDF conversion with tables preserved.", "x", [], 0),
            ("PDF conversion with tables preserved.", "x", ["--strict"], 1),
            (
                "PDF conversion with tables preserved.",
                "x",
                ["--strict", "--ignore", "description-no-when,description-short"],
                0,
            ),
        ]
        for description, name, options, expected in cases:
            self.make_skill("x", name, description)
            for fmt in ("text", "json", "github", "sarif"):
                with self.subTest(name=name, options=options, fmt=fmt):
                    argv = ["lint", str(self.root), "--format", fmt] + options
                    code, plain, _ = run(argv)
                    suggest_code, suggested, _ = run(argv + ["--suggest"])
                    self.assertEqual(code, expected)
                    self.assertEqual(suggest_code, code)
                    if fmt == "github":
                        # one annotation per finding either way; the suggestion rides in the message
                        pairs = zip(plain.splitlines(), suggested.splitlines(), strict=True)
                        for before, after in pairs:
                            self.assertTrue(after.startswith(before))
                        if name == "My_Skill":
                            self.assertIn('%0A+ name: "x"', suggested)
                    elif fmt == "text":
                        self.assertEqual(suggested.splitlines()[-1], plain.splitlines()[-1])
                    elif fmt == "sarif":
                        self.assertEqual(
                            len(json.loads(suggested)["runs"][0]["results"]),
                            len(json.loads(plain)["runs"][0]["results"]),
                        )
                    else:
                        self.assertEqual(json.loads(suggested)["stats"], json.loads(plain)["stats"])
        for options in ([], ["--suggest"]):
            self.assertEqual(run(["lint", str(self.root / "empty")] + options)[0], 2)

    def test_sarif_format_clean_exit_zero(self):
        self.make_skill("csv-summary", "csv-summary", GOOD)
        code, out, _ = run(["lint", "--format", "sarif", str(self.root)])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["version"], "2.1.0")
        self.assertEqual(data["$schema"], "https://json.schemastore.org/sarif-2.1.0.json")
        run_entry = data["runs"][0]
        self.assertEqual(run_entry["tool"]["driver"]["name"], "stb")
        self.assertEqual(run_entry["tool"]["driver"]["rules"], [])
        self.assertEqual(run_entry["results"], [])

    def test_sarif_format_with_findings(self):
        self.make_skill("x", extra="license: MIT")
        code, out, _ = run(["lint", "--format", "sarif", str(self.root)])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["version"], "2.1.0")
        run_entry = data["runs"][0]
        self.assertEqual(run_entry["tool"]["driver"]["name"], "stb")
        rules = run_entry["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        self.assertIn("description-missing", rule_ids)
        results = run_entry["results"]
        self.assertTrue(results)
        desc_res = next(r for r in results if r["ruleId"] == "description-missing")
        self.assertEqual(desc_res["level"], "error")
        self.assertIn("description", desc_res["message"]["text"])
        self.assertTrue(desc_res["locations"])
        uri = desc_res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        self.assertTrue(uri.endswith("SKILL.md"))
        self.assertNotIn("\\", uri)

    def test_github_format_error(self):
        self.make_skill("x", extra="license: MIT")
        text_code, _, _ = run(["lint", str(self.root)])
        code, out, _ = run(["lint", "--format", "github", str(self.root)])
        self.assertEqual(code, text_code)
        self.assertEqual(code, 1)
        lines = [ln for ln in out.splitlines() if ln.startswith("::")]
        self.assertTrue(lines)
        self.assertTrue(
            any(
                ln.startswith("::error file=")
                and "title=description-missing::" in ln
                and "frontmatter has no 'description'" in ln
                for ln in lines
            )
        )

    def test_github_format_warning_notice_and_pathless(self):
        self.make_skill("csv-summary", "csv-summary", GOOD + " <tag>")
        code, out, _ = run(["lint", "--format", "github", "--budget", "10", str(self.root)])
        self.assertEqual(code, 1)
        lines = out.splitlines()
        notices = [ln for ln in lines if ln.startswith("::notice file=") and "title=description-angle-brackets::" in ln]
        self.assertTrue(notices)
        pathless = [ln for ln in lines if "title=description-budget::" in ln]
        self.assertTrue(pathless)
        for ln in pathless:
            self.assertNotIn("file=", ln)

    def test_github_format_clean_exit_zero(self):
        self.make_skill("csv-summary", "csv-summary", GOOD)
        text_code, _, _ = run(["lint", str(self.root)])
        code, out, _ = run(["lint", "--format", "github", str(self.root)])
        self.assertEqual(code, text_code)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_github_format_escapes_workflow_command_syntax(self):
        from skill_trigger_bench.cli import _github_escape_data, _github_escape_prop

        # a newline or % in a message would otherwise end or corrupt the annotation
        self.assertEqual(_github_escape_data("50% done\nnext"), "50%25 done%0Anext")
        # : and , separate properties, so they must be escaped inside file= and title=
        self.assertEqual(_github_escape_prop("a:b,c"), "a%3Ab%2Cc")

    def test_no_skills_in_explicit_path(self):
        self.assertEqual(run(["lint", str(self.root / "empty")])[0], 2)

    def test_eval_dry_run_needs_no_model(self):
        d = self.make_skill("csv-summary", "csv-summary", GOOD)
        code, out, _ = run(["eval", str(d), "--dry-run", "-n", "3"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["should_not_trigger"]), 3)

    def test_eval_rejects_broken_skill(self):
        d = self.make_skill("x", raw="nothing")
        self.assertEqual(run(["eval", str(d), "--dry-run"])[0], 2)

    def test_eval_rates_must_be_fractions(self):
        d = self.make_skill("csv-summary", "csv-summary", GOOD)
        for bad in ("80", "80%", "-0.1", "lots"):
            with self.subTest(bad=bad), self.assertRaises(SystemExit) as cm:
                run(["eval", str(d), "--dry-run", "--min-trigger", bad])
            self.assertEqual(cm.exception.code, 2)
        self.assertEqual(run(["eval", str(d), "--dry-run", "--max-false", "0.1"])[0], 0)

    def test_eval_with_path_without_skills(self):
        d = self.make_skill("csv-summary", "csv-summary", GOOD)
        code, _, err = run(["eval", str(d), "--dry-run", "--with", str(self.root / "nope")])
        self.assertEqual(code, 2)
        self.assertIn("no skills found", err)

    def test_eval_html_folder_checked_before_model_calls(self):
        d = self.make_skill("csv-summary", "csv-summary", GOOD)
        with patch("skill_trigger_bench.cli.run_eval") as ev:
            code, _, err = run(["eval", str(d), "--html", str(self.root / "missing" / "r.html")])
        self.assertEqual(code, 2)
        self.assertIn("does not exist", err)
        ev.assert_not_called()

    def test_eval_max_prompts_cap(self):
        d = self.make_skill("csv-summary", "csv-summary", GOOD)
        code, _, err = run(["eval", str(d), "-n", "5", "--max-prompts", "2", "--runner", "claude"])
        self.assertEqual(code, 2)
