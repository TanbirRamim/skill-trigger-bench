import json
from pathlib import PurePosixPath

from skill_trigger_bench.frontmatter import load_yaml
from skill_trigger_bench.lint import NAME_RE, Finding, _check_frontmatter, lint, referenced_files
from skill_trigger_bench.skills import Skill, collect, find_skills, plugin_skill_dirs

from .helpers import SkillDirCase

GOOD = "Summarize CSV files with column types. Use when the user asks what is in a CSV file."


def rules(findings):
    return [f.rule for f in findings]


class LintTests(SkillDirCase):
    def run_lint(self, **kw):
        return lint(find_skills(self.root), **kw)

    def test_clean_skill_has_no_findings(self):
        self.make_skill("csv-summary", "csv-summary", GOOD)
        findings, stats = self.run_lint()
        self.assertEqual(findings, [])
        self.assertEqual(stats["errors"], 0)

    def test_missing_frontmatter(self):
        self.make_skill("x", raw="# no frontmatter\n")
        self.assertEqual(rules(self.run_lint()[0]), ["frontmatter"])

    def test_missing_name_and_description(self):
        self.make_skill("x", extra="license: MIT")
        r = rules(self.run_lint()[0])
        self.assertIn("name-missing", r)
        self.assertIn("description-missing", r)

    def test_name_too_long(self):
        n = "a" * 65
        self.make_skill(n, n, GOOD)
        self.assertIn("name-length", rules(self.run_lint()[0]))

    def test_name_bad_format(self):
        self.make_skill("PDF_Tool", "PDF_Tool", GOOD)
        self.assertIn("name-format", rules(self.run_lint()[0]))

    def test_name_double_hyphen(self):
        self.make_skill("a--b", "a--b", GOOD)
        self.assertIn("name-format", rules(self.run_lint()[0]))

    def test_name_dir_mismatch_is_warning(self):
        self.make_skill("folder", "other-name", GOOD)
        f = [x for x in self.run_lint()[0] if x.rule == "name-dir-mismatch"]
        self.assertEqual(f[0].severity, "warning")

    def test_name_mismatch_suggestion(self):
        self.make_skill("folder", "other-name", GOOD)
        finding = next(f for f in self.run_lint()[0] if f.rule == "name-dir-mismatch")
        self.assertEqual(finding.suggestion, '- name: "other-name"\n+ name: "folder"')

    def test_name_format_suggestions(self):
        for name, expected in [
            ("My_Skill", "my-skill"),
            (" A__B--C! ", "a-b-c"),
            ("Café", "cafe"),
            ("a" * 64 + "_b", "a" * 64),
        ]:
            with self.subTest(name=name):
                self.make_skill("folder", description=GOOD, extra="name: " + json.dumps(name, ensure_ascii=False))
                finding = next(f for f in self.run_lint()[0] if f.rule == "name-format")
                self.assertEqual(finding.suggestion.splitlines()[-1], '+ name: "' + expected + '"')
                self.assertRegex(expected, NAME_RE)
        self.make_skill("folder", description=GOOD, extra='name: "!!!"')
        finding = next(f for f in self.run_lint()[0] if f.rule == "name-format")
        self.assertEqual(finding.suggestion, "")
        self.assertNotIn("suggestion", finding.to_dict())

    def test_description_suggestions(self):
        for description, topic in [
            ("Converts PDF documents into clean Markdown with tables preserved.", "PDF documents"),
            ("PDF conversion with tables preserved and readable Markdown output.", "PDF conversion"),
        ]:
            with self.subTest(description=description):
                self.make_skill("x", "x", description)
                finding = next(f for f in self.run_lint()[0] if f.rule == "description-no-when")
                self.assertEqual(
                    finding.suggestion,
                    f'Draft (review topic and trigger condition):\n+ Use when the user\'s request concerns "{topic}".',
                )
        for excess in (1, 76):
            self.make_skill("x", "x", "Use when testing. " + "x" * (1024 + excess - 18))
            finding = next(f for f in self.run_lint()[0] if f.rule == "description-length")
            self.assertEqual(finding.suggestion, f"+ Remove {excess} characters to meet the 1024-character limit.")

    def test_description_suggestion_verbs(self):
        verbs = (
            "Convert",
            "Converts",
            "Process",
            "Processes",
            "Summarize",
            "Summarizes",
            "Summarise",
            "Summarises",
            "Create",
            "Creates",
            "Generate",
            "Generates",
            "Analyze",
            "Analyzes",
            "Analyse",
            "Analyses",
            "Manage",
            "Manages",
            "Validate",
            "Validates",
            "Extract",
            "Extracts",
        )
        for verb in verbs:
            with self.subTest(verb=verb):
                self.make_skill("x", "x", f"{verb} PDF documents with tables preserved.")
                finding = next(f for f in self.run_lint()[0] if f.rule == "description-no-when")
                self.assertIn("Draft (review topic and trigger condition):", finding.suggestion)
                self.assertIn('concerns "PDF documents".', finding.suggestion)

    def test_description_suggestion_uncertain_topic(self):
        for description in (
            "I can help you do anything.",
            "Works wonders for everyone.",
            "Converts things into something useful.",
            "Processes quickly.",
            "Converts.",
            "...",
            "Creates reports and sends emails.",
            "Helps create PDF documents.",
            "Automatically converts PDF documents.",
        ):
            with self.subTest(description=description):
                self.make_skill("x", "x", description)
                finding = next(f for f in self.run_lint()[0] if f.rule == "description-no-when")
                self.assertEqual(
                    finding.suggestion,
                    "Draft (review topic and trigger condition):\n"
                    "+ Use when [describe the request that should trigger this skill].",
                )

    def test_name_suggestions_preserve_yaml_string_values(self):
        for value in (
            "true",
            "false",
            "null",
            "yes",
            "no",
            "on",
            "off",
            "123",
            "2026-10-11",
            "a: b # comment",
            "[a, b]",
            "*alias",
            "&anchor",
            "!tag",
            "|",
            ">",
            'a"b',
            "a'b",
            "a\\b",
            "line\nnext",
        ):
            with self.subTest(value=value):
                skill = Skill(self.root / "target" / "SKILL.md", meta={"name": value, "description": GOOD})
                finding = next(f for f in _check_frontmatter(skill) if f.rule == "name-dir-mismatch")
                lines = finding.suggestion.splitlines()
                self.assertEqual(len(lines), 2)
                self.assertEqual(load_yaml(lines[0][2:]), {"name": value})
                self.assertEqual(load_yaml(lines[1][2:]), {"name": "target"})
                skill.meta["name"] = "old-name"
                # Use a pure path so Windows drive/separator syntax cannot alter the test value.
                skill.path = PurePosixPath("/skills") / value / "SKILL.md"
                finding = next(f for f in _check_frontmatter(skill) if f.rule == "name-dir-mismatch")
                self.assertEqual(load_yaml(finding.suggestion.splitlines()[1][2:]), {"name": value})

    def test_name_suggestion_escapes_yaml_unicode_line_breaks(self):
        for char in ("\u007f", "\u0080", "\u0085", "\u009f", "\u2028", "\u2029"):
            value = "a" + char + "b"
            skill = Skill(self.root / "target" / "SKILL.md", meta={"name": value, "description": GOOD})
            finding = next(f for f in _check_frontmatter(skill) if f.rule == "name-dir-mismatch")
            self.assertEqual(len(finding.suggestion.splitlines()), 2)
            self.assertEqual(json.loads(finding.suggestion.splitlines()[0][8:]), value)

    def test_empty_slug_has_no_suggestion(self):
        for value in ("!!!", "___", "---", "\u4e2d\u6587"):
            with self.subTest(value=value):
                skill = Skill(self.root / "x" / "SKILL.md", meta={"name": value, "description": GOOD})
                finding = next(f for f in _check_frontmatter(skill) if f.rule == "name-format")
                self.assertEqual(finding.suggestion, "")
                self.assertNotIn("suggestion", finding.to_dict())

    def test_description_length_uses_stripped_character_count(self):
        for excess in (0, 1, 37):
            description = "  " + "Use when testing. " + "\u00e9" * (1024 + excess - 18) + "  "
            skill = Skill(self.root / "x" / "SKILL.md", meta={"name": "x", "description": description})
            findings = [f for f in _check_frontmatter(skill) if f.rule == "description-length"]
            if excess:
                self.assertEqual(
                    findings[0].suggestion, f"+ Remove {excess} characters to meet the 1024-character limit."
                )
            else:
                self.assertEqual(findings, [])

    def test_finding_serialization_without_suggestion(self):
        self.assertEqual(
            Finding("rule", "info", "skill", "message").to_dict(),
            {"rule": "rule", "severity": "info", "skill": "skill", "message": "message"},
        )
        self.assertEqual(
            Finding("rule", "warning", "skill", "message", "path", "other").to_dict(),
            {
                "rule": "rule",
                "severity": "warning",
                "skill": "skill",
                "message": "message",
                "path": "path",
                "other": "other",
            },
        )

    def test_suggestions_do_not_modify_files(self):
        self.make_skill("folder", "My_Skill", "PDF conversion with tables preserved. " + "x" * 1024)
        self.make_skill("clean", "clean", GOOD)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        findings, _ = self.run_lint()
        self.assertEqual(
            {f.rule for f in findings if f.suggestion},
            {"name-format", "name-dir-mismatch", "description-no-when", "description-length"},
        )
        self.assertEqual(
            before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        )

    def test_description_too_long(self):
        self.make_skill("x", "x", "Use when testing. " + "word " * 220)
        self.assertIn("description-length", rules(self.run_lint()[0]))

    def test_description_short(self):
        self.make_skill("x", "x", "Use when x.")
        self.assertIn("description-short", rules(self.run_lint()[0]))

    def test_description_without_when(self):
        self.make_skill("x", "x", "Converts PDF documents into clean Markdown with tables preserved.")
        self.assertIn("description-no-when", rules(self.run_lint()[0]))

    def test_description_with_when_variants(self):
        for i, d in enumerate(
            [
                "Converts PDF documents into Markdown. Use for any PDF the user drops in.",
                "Converts PDF documents into Markdown whenever a PDF shows up in the chat.",
                "Converts PDF documents into Markdown if the user uploads a scanned document.",
                "Triggers on requests to turn PDF documents into Markdown text.",
            ]
        ):
            self.make_skill(f"s{i}", f"s{i}", d)
        self.assertNotIn("description-no-when", rules(self.run_lint(overlap=1.1)[0]))

    def test_compatibility_length(self):
        self.make_skill("x", "x", GOOD, extra="compatibility: " + "y" * 501)
        self.assertIn("compatibility-length", rules(self.run_lint()[0]))

    def test_folded_description_is_read(self):
        self.make_skill(
            "x", raw="---\nname: x\ndescription: >\n  Summarize CSV files.\n  Use when asked about a CSV.\n---\n"
        )
        self.assertEqual(find_skills(self.root)[0].description, "Summarize CSV files. Use when asked about a CSV.")

    def test_body_too_long(self):
        self.make_skill("x", "x", GOOD, body="line\n" * 30)
        self.assertIn("body-too-long", rules(self.run_lint(max_lines=20)[0]))

    def test_missing_link_is_error(self):
        self.make_skill("x", "x", GOOD, body="See [the guide](references/guide.md).\n")
        f = [x for x in self.run_lint()[0] if x.rule == "missing-reference"]
        self.assertEqual(f[0].severity, "error")

    def test_existing_link_is_fine(self):
        d = self.make_skill("x", "x", GOOD, body="See [the guide](references/guide.md#top).\n")
        (d / "references").mkdir()
        (d / "references" / "guide.md").write_text("hi")
        self.assertNotIn("missing-reference", rules(self.run_lint()[0]))

    def test_bare_path_found_in_sibling_skill_is_fine(self):
        self.make_skill("a", "a", GOOD, body="Run `/b` and read `references/shared.md`.\n")
        d = self.make_skill("b", "b", "Bake bread at home. Use when the user wants sourdough tips.")
        (d / "references").mkdir()
        (d / "references" / "shared.md").write_text("hi")
        self.assertNotIn("missing-reference", rules(self.run_lint()[0]))

    def test_bare_path_missing_everywhere_is_warning(self):
        self.make_skill("a", "a", GOOD, body="Run scripts/build.py first.\n")
        f = [x for x in self.run_lint()[0] if x.rule == "missing-reference"]
        self.assertEqual(f[0].severity, "warning")

    def test_urls_and_code_fences_ignored(self):
        refs = referenced_files("[x](https://e.com/a.md) [y](#anchor)\n```\nscripts/in_fence.py\n```\n[z](/abs.md)\n")
        self.assertEqual(refs, [])

    def test_links_in_code_and_placeholders_ignored(self):
        body = (
            "> Also see: [Title](URL) and [notes](path).\n"
            "Use `[x](missing.md)` in your own skill.\n"
            "```python\n"
            "subprocess.Popen(['id'],shell=True,stdout=-1)\n"
            "[a](in_fence.md)\n"
            "```\n"
            "[real](references/real.md)\n"
        )
        self.assertEqual(referenced_files(body), [("references/real.md", True)])

    def test_description_use_during(self):
        self.make_skill("x", "x", "EU AI Act readiness check. Use during AI-system intake or before EU deployment.")
        self.assertNotIn("description-no-when", rules(self.run_lint()[0]))

    def test_description_point_of_view_first_person(self):
        self.make_skill("x", "x", "I can help you process PDFs")
        f = [x for x in self.run_lint()[0] if x.rule == "description-point-of-view"]
        self.assertEqual(f[0].severity, "warning")

    def test_description_point_of_view_second_person(self):
        self.make_skill("x", "x", "You can use this to process PDFs")
        f = [x for x in self.run_lint()[0] if x.rule == "description-point-of-view"]
        self.assertEqual(f[0].severity, "warning")

    def test_description_point_of_view_third_person_is_fine(self):
        self.make_skill("x", "x", "Processes PDFs. Use when the user mentions PDFs.")
        self.assertNotIn("description-point-of-view", rules(self.run_lint()[0]))

    def test_description_filler_start_fires(self):
        for description in [
            "This skill summarises CSV files. Use when the user asks about a CSV.",
            "A skill that converts PDFs to Markdown. Use when the user mentions PDFs.",
            "This is a skill for tidying git branches. Use when branches pile up.",
            "Skill for transcribing audio recordings. Use when the user has audio.",
            "Skill to batch-resize images. Use when the user has many images.",
            "this skill summarises CSV files in lowercase.",
        ]:
            with self.subTest(description=description):
                self.make_skill("x", "x", description)
                f = [x for x in self.run_lint()[0] if x.rule == "description-filler-start"]
                self.assertEqual(len(f), 1)
                self.assertEqual(f[0].severity, "info")

    def test_description_filler_start_message_counts_characters(self):
        self.make_skill("x", "x", "This skill summarises CSV files. Use when the user asks about a CSV.")
        finding = next(f for f in self.run_lint()[0] if f.rule == "description-filler-start")
        self.assertIn("costs 11 characters", finding.message)

    def test_description_task_first_is_fine(self):
        for description in [
            "Summarise CSV files. Use when the user asks what is in a CSV file.",
            "Thistle garden planner. Use when the user mentions thistles.",
            "These skills list helper. Use when the user asks about these skills.",
        ]:
            with self.subTest(description=description):
                self.make_skill("x", "x", description)
                self.assertNotIn("description-filler-start", rules(self.run_lint()[0]))

    def test_description_point_of_view_ignores_quoted_user_phrases(self):
        self.make_skill("x", "x", 'Summarises papers. Use when the user says "tell me about this paper".')
        self.assertNotIn("description-point-of-view", rules(self.run_lint()[0]))

    def test_description_point_of_view_apostrophes_are_not_quotes(self):
        self.make_skill("x", "x", "I'll help you clean CSVs, it's quick")
        self.assertIn("description-point-of-view", rules(self.run_lint()[0]))

    def test_description_point_of_view_use_when_you_is_fine(self):
        self.make_skill("x", "x", "Converts PDFs into Markdown. Use when you upload a scanned document.")
        self.assertNotIn("description-point-of-view", rules(self.run_lint()[0]))

    def test_duplicate_identical_copies_named(self):
        self.make_skill("one/pdf", "pdf", GOOD)
        self.make_skill("two/pdf", "pdf", GOOD)
        self.make_skill("three/doc", "doc", GOOD)
        self.make_skill("four/doc", "doc", GOOD, body="different\n")
        msgs = {f.skill: f.message for f in self.run_lint()[0] if f.rule == "duplicate-name"}
        self.assertIn("identical copies", msgs["pdf"])
        self.assertIn("share this name", msgs["doc"])

    def test_symlink_loop_does_not_hang(self):
        import os

        self.make_skill("pack/a", "a", GOOD)
        os.symlink("..", self.root / "pack" / "loop")
        os.symlink(self.root / "pack", self.root / "pack-again")
        self.assertEqual([s.name for s in find_skills(self.root)], ["a"])

    def test_template_paths_ignored(self):
        self.assertEqual(referenced_files("[x](references/{name}.md) [y](references/*.md)"), [])

    def test_duplicate_names(self):
        self.make_skill("one/pdf", "pdf", GOOD)
        self.make_skill("two/pdf", "pdf", GOOD)
        r = rules(self.run_lint()[0])
        self.assertIn("duplicate-name", r)
        self.assertNotIn("trigger-overlap", r)

    def test_budget_over(self):
        for i in range(5):
            self.make_skill(f"s{i}", f"s{i}", f"Topic{i} " + f"unique{i} " * 30 + "Use when needed.")
        findings, stats = self.run_lint(budget=500, overlap=1.1)
        f = [x for x in findings if x.rule == "description-budget"]
        self.assertEqual(f[0].severity, "error")
        self.assertGreater(stats["description_chars"], 500)

    def test_budget_near_limit_warns(self):
        self.make_skill("x", "x", GOOD)
        f = [x for x in self.run_lint(budget=len(GOOD) + 10)[0] if x.rule == "description-budget"]
        self.assertEqual(f[0].severity, "warning")

    def test_trigger_overlap_reports_pair(self):
        self.make_skill(
            "resend", "resend", "Send transactional email with the Resend API, webhooks, domains. Use when emailing."
        )
        self.make_skill(
            "resend-cli",
            "resend-cli",
            "Send email with the Resend CLI: webhooks, domains, templates. Use when emailing from a terminal.",
        )
        self.make_skill("bread", "bread", "Bake sourdough bread. Use when the user asks about baking.")
        findings, stats = self.run_lint()
        self.assertEqual(len(stats["overlapping_pairs"]), 1)
        pair = stats["overlapping_pairs"][0]
        self.assertEqual({pair["a"], pair["b"]}, {"resend", "resend-cli"})
        self.assertIn("resend", pair["shared"])

    def test_errors_sorted_first(self):
        self.make_skill("x", "x", "Converts PDF documents into Markdown with tables preserved nicely.")
        self.make_skill("y", extra="license: MIT")
        findings, _ = self.run_lint()
        self.assertEqual(findings[0].severity, "error")


class DiscoveryTests(SkillDirCase):
    def test_single_skill_dir(self):
        d = self.make_skill("x", "x", GOOD)
        self.assertEqual(len(find_skills(d)), 1)

    def test_nested_and_resources_not_scanned(self):
        d = self.make_skill("pack/a", "a", GOOD)
        self.make_skill("pack/b", "b", GOOD)
        (d / "examples" / "inner").mkdir(parents=True)
        (d / "examples" / "inner" / "SKILL.md").write_text("---\nname: inner\n---\n")
        self.assertEqual(sorted(s.name for s in find_skills(self.root)), ["a", "b"])

    def test_collect_dedupes(self):
        self.make_skill("x", "x", GOOD)
        self.assertEqual(len(collect([str(self.root), str(self.root / "x")])), 1)

    def test_missing_dir_is_empty(self):
        self.assertEqual(find_skills(self.root / "nope"), [])

    def test_plugin_dirs_from_manifest(self):
        plug = self.root / "cache" / "acme" / "1.0"
        self.make_skill("cache/acme/1.0/skills/thing", "thing", GOOD)
        (self.root / "plugins").mkdir()
        (self.root / "plugins" / "installed_plugins.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "plugins": {"acme@market": [{"installPath": str(plug)}], "gone@m": [{"installPath": "/nope"}]},
                }
            )
        )
        self.assertEqual(plugin_skill_dirs(self.root), [("acme", plug / "skills")])

    def test_plugin_manifest_missing(self):
        self.assertEqual(plugin_skill_dirs(self.root), [])
