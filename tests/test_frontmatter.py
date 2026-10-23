import unittest

from skill_trigger_bench.frontmatter import FrontmatterError, parse_simple_yaml, split_frontmatter


class SplitTests(unittest.TestCase):
    def test_no_frontmatter(self):
        fm, body, line = split_frontmatter("# hello\n")
        self.assertIsNone(fm)
        self.assertEqual(body, "# hello\n")

    def test_basic_split_and_body_line(self):
        fm, body, line = split_frontmatter("---\nname: a\n---\nbody\n")
        self.assertEqual(fm, "name: a")
        self.assertEqual(body.strip(), "body")
        self.assertEqual(line, 4)

    def test_unclosed(self):
        with self.assertRaises(FrontmatterError):
            split_frontmatter("---\nname: a\n")

    def test_bom_is_ignored(self):
        fm, _, _ = split_frontmatter("﻿---\nname: a\n---\n")
        self.assertEqual(fm, "name: a")


class SimpleYamlTests(unittest.TestCase):
    def test_colon_in_plain_value_is_an_error(self):
        # PyYAML rejects these too, so the fallback must not quietly accept them.
        for text in [
            "description: Send email with the CLI: webhooks",
            "description: Use when emailing\n  from the CLI: webhooks",
            "description: ends with a colon:",
        ]:
            with self.subTest(text=text), self.assertRaises(FrontmatterError):
                parse_simple_yaml(text)

    def test_colon_without_space_or_in_comment_is_fine(self):
        d = parse_simple_yaml("url: https://example.com/a\ntime: 12:30\nnote: ok # see: docs")
        self.assertEqual(d, {"url": "https://example.com/a", "time": "12:30", "note": "ok"})

    def test_plain_and_quoted(self):
        d = parse_simple_yaml("name: pdf\ndescription: \"Use when: things\"\nother: 'it''s'")
        self.assertEqual(d, {"name": "pdf", "description": "Use when: things", "other": "it's"})

    def test_folded_block(self):
        d = parse_simple_yaml("description: >\n  line one\n  line two\nname: x\n")
        self.assertEqual(d["description"], "line one line two")
        self.assertEqual(d["name"], "x")

    def test_literal_block(self):
        d = parse_simple_yaml("description: |\n  a\n  b\n")
        self.assertEqual(d["description"], "a\nb")

    def test_nested_map(self):
        d = parse_simple_yaml("metadata:\n    author: resend\n    version: 2\nlicense: MIT")
        self.assertEqual(d["metadata"], {"author": "resend", "version": 2})
        self.assertEqual(d["license"], "MIT")

    def test_lists(self):
        d = parse_simple_yaml('should_trigger:\n  - "one"\n  - two\nshould_not_trigger: []\n')
        self.assertEqual(d["should_trigger"], ["one", "two"])
        self.assertEqual(d["should_not_trigger"], [])

    def test_plain_multiline_scalar(self):
        d = parse_simple_yaml("description: first part\n  second part\nname: z")
        self.assertEqual(d["description"], "first part second part")

    def test_comments_and_bools(self):
        d = parse_simple_yaml("# c\na: true  # yes\nb: null\n")
        self.assertEqual(d, {"a": True, "b": None})

    def test_garbage_raises(self):
        with self.assertRaises(FrontmatterError):
            parse_simple_yaml("just some text without a colon")
