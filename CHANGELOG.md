# Changelog

## Unreleased

## v0.2.1 (2026-10-23)

- `stb eval` checks its arguments before spending model calls: `--min-trigger 80` or `80%` is rejected with a hint that rates are 0..1 (before, it just failed every run), `--with` a path that has no skills is an error instead of being silently dropped, and a missing folder for `--html` is caught up front instead of crashing after the run.
- `stb lint` now reports an unquoted value with `: ` in it (like `description: Use the CLI: fast`) as a frontmatter error even without PyYAML installed. Real YAML parsers reject that line, so the skill silently fails to load.

## v0.2.0 (2026-10-23)

- New lint rule `description-filler-start`: flags descriptions that open with filler like "This skill..." (#19, thanks @chiragjangiir)
- `stb lint --format sarif` writes SARIF 2.1.0, so findings show up in GitHub code scanning (#21, thanks @chiragjangiir)
- `stb eval --html` exports a standalone HTML report (#23, thanks @chiragjangiir)
- Gemini CLI runner for `stb eval` (#24, thanks @chiragjangiir)
- Gemini runner parses stream-json `tool_use` / `activate_skill` events and uses `GEMINI_CLI_HOME` for isolation (#26)

## v0.1.0 (2026-10-13)

First tagged release: `stb lint`, `--suggest` (thanks @Pranitha06sri) and a composite GitHub Action (thanks @yesheng-oss).
