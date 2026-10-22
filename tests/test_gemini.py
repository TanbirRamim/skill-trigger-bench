import subprocess
from pathlib import Path
from unittest import mock

from skill_trigger_bench.cli import build_parser
from skill_trigger_bench.runners import RUNNERS, GeminiRunner, RunnerError
from skill_trigger_bench.stream import parse_gemini_text

from .helpers import SkillDirCase, fixture


class GeminiParseTests(SkillDirCase):
    def test_activation(self):
        t = parse_gemini_text(fixture("gemini_trigger.jsonl"))
        self.assertTrue(t.finished)
        self.assertFalse(t.is_error)
        self.assertEqual(t.skill_calls, ["csv-summary"])
        self.assertTrue(t.activated("csv-summary"))
        self.assertEqual(t.tool_calls, ["Skill"])
        self.assertEqual(t.result, "Using the csv-summary skill.")

    def test_no_activation(self):
        t = parse_gemini_text(fixture("gemini_no_trigger.jsonl"))
        self.assertTrue(t.finished)
        self.assertEqual(t.skill_calls, [])
        self.assertFalse(t.activated("csv-summary"))
        self.assertEqual(t.result, "I am doing well, how can I help you today?")

    def test_other_skill(self):
        t = parse_gemini_text(fixture("gemini_other_skill.jsonl"))
        self.assertEqual(t.first_skill(), "bread")
        self.assertFalse(t.activated("csv-summary"))

    def test_folder_mapped_to_frontmatter_name(self):
        t = parse_gemini_text(fixture("gemini_other_skill.jsonl"), {"bread": "sourdough"})
        self.assertEqual(t.skill_calls, ["sourdough"])

    def test_error(self):
        t = parse_gemini_text(fixture("gemini_error.jsonl"))
        self.assertTrue(t.is_error)
        self.assertIn("401", t.result)

    def test_bad_lines(self):
        t = parse_gemini_text("not json\n" + fixture("gemini_no_trigger.jsonl"))
        self.assertEqual(t.bad_lines, 1)


class GeminiRunnerTests(SkillDirCase):
    def _run(self, stdout, code=0):
        skill = self.make_skill("csv", "csv-summary", "Summarize a CSV file.")
        seen = {}

        def fake(cmd, cwd, env, **kw):
            seen.update(cmd=cmd, cwd=Path(cwd), env=env)
            seen["installed"] = (Path(cwd) / ".gemini/skills/csv/SKILL.md").is_file()
            return subprocess.CompletedProcess(cmd, code, stdout, "boom")

        with mock.patch("skill_trigger_bench.runners.subprocess.run", side_effect=fake):
            t = GeminiRunner().run("hi", [skill])
        return t, seen

    def test_registered_as_agent(self):
        self.assertIs(RUNNERS["gemini"], GeminiRunner)
        args = build_parser().parse_args(["eval", "x", "--agent", "gemini"])
        self.assertEqual(args.runner, "gemini")

    def test_sandbox_and_flags(self):
        out = fixture("gemini_trigger.jsonl")
        t, seen = self._run(out)
        self.assertTrue(seen["installed"])
        self.assertEqual(t.skill_calls, ["csv-summary"])
        cmd = seen["cmd"]
        self.assertEqual(cmd[:2], ["gemini", "-p"])
        self.assertIn("--output-format", cmd)
        self.assertIn("stream-json", cmd)
        self.assertEqual(seen["env"]["GEMINI_HOME"], str(seen["cwd"] / ".gemini"))
        self.assertFalse(seen["cwd"].exists())

    def test_available_is_false_when_gemini_missing(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(GeminiRunner().available())

    def test_error_raises(self):
        with self.assertRaises(RunnerError):
            self._run(fixture("gemini_error.jsonl"), code=1)
