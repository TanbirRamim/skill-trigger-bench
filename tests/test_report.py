import json
from pathlib import Path

from skill_trigger_bench.cli import main
from skill_trigger_bench.evaluate import EvalReport, PromptResult, run_eval
from skill_trigger_bench.prompts import PromptSet
from skill_trigger_bench.report import generate_html_report
from skill_trigger_bench.runners import ReplayRunner
from skill_trigger_bench.skills import find_skills

from .helpers import SkillDirCase, fixture

DESC = "Summarize CSV files. Use when the user asks what is in a CSV."


class ReportTests(SkillDirCase):
    def test_generate_html_report_structure_and_escaping(self):
        report = EvalReport(
            skill="test-skill",
            runner="replay",
            results=[
                PromptResult(
                    prompt="<script>alert('xss')</script> & test",
                    expected=True,
                    triggered=True,
                    skill_calls=["test-skill"],
                    cost_usd=0.0042,
                ),
                PromptResult(
                    prompt="plain question",
                    expected=False,
                    triggered=False,
                    skill_calls=[],
                ),
            ],
            skill_not_loaded=False,
        )

        html_out = generate_html_report(report, min_trigger=0.8, max_false=0.2, model="mock-model")

        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("<title>stb eval: test-skill (PASS)</title>", html_out)
        self.assertIn("PASS", html_out)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; &amp; test", html_out)
        self.assertNotIn("<script>alert", html_out)
        self.assertIn("100%", html_out)
        self.assertIn("0%", html_out)
        self.assertIn("$0.0042", html_out)
        self.assertIn("mock-model", html_out)

    def test_generate_html_report_fail_and_errors(self):
        report = EvalReport(
            skill="broken-skill",
            runner="replay",
            results=[
                PromptResult(
                    prompt="bad run",
                    expected=True,
                    triggered=None,
                    error="Timeout exceeded",
                ),
            ],
            skill_not_loaded=True,
        )

        html_out = generate_html_report(report, min_trigger=0.8, max_false=0.2)
        self.assertIn("FAIL", html_out)
        self.assertIn("n/a", html_out)
        self.assertIn("⚠️ 1 prompt(s) failed with runtime errors.", html_out)
        self.assertIn("The agent did not list this skill as loaded", html_out)
        self.assertIn("Timeout exceeded", html_out)

    def test_cli_eval_generates_html(self):
        skill_dir = self.make_skill("csv-summary", "csv-summary", DESC)
        prompts_file = self.root / "prompts.json"
        prompts_file.write_text(
            json.dumps({"should_trigger": ["summarize a.csv"], "should_not_trigger": ["bake a cake"]})
        )
        html_out_path = self.root / "report.html"

        # Patch ReplayRunner in RUNNERS to use fixtures
        replay = ReplayRunner(
            transcripts=[
                fixture("claude_trigger.jsonl"),
                fixture("claude_no_trigger.jsonl"),
            ]
        )
        from unittest.mock import patch

        with patch.dict("skill_trigger_bench.cli.RUNNERS", {"claude": lambda **kw: replay}):
            code = main(["eval", str(skill_dir), "--prompts", str(prompts_file), "--html", str(html_out_path)])

        self.assertEqual(code, 0)
        self.assertTrue(html_out_path.exists())
        content = html_out_path.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("csv-summary", content)
        self.assertIn("summarize a.csv", content)
        self.assertIn("bake a cake", content)
