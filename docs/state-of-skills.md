# State of public skills, October 2026

_Last refreshed 2026-10-23 with `stb` 0.2.0 (master at c4cf32b). First run: 2026-10-09._

I ran `stb lint` over the most-starred public skill repos to see what the static checks
find on real packs, and what happens when you install several of them at once. Everything
here is offline: no model calls, nothing from the repos was executed.

Short version: the single-purpose packs are in good shape. Problems show up in two places:
very large packs, and installing more than one pack. Almost all of it is fixable with a
text edit.

## How this was run

Shallow clones taken on 2026-10-23 (stars read from the GitHub API the same day):

| repo | stars | commit (2026-10-23) | commit (2026-10-09) |
|---|---:|---|---|
| obra/superpowers | 303,791 | 2ce8aa1 | 8ca22db |
| anthropics/skills | 183,071 | dbd4588 | 9d63080 |
| ComposioHQ/awesome-claude-skills | 77,702 | be2a406 | be2a406 |
| alirezarezvani/claude-skills | 28,562 | 27cfcd0 | 19392f7 |
| nidhinjs/prompt-master | 14,897 | 49b3a72 | 2bd9251 |
| Jeffallan/claude-skills | 12,012 | 02b0502 | 1be15d8 |
| SnailSploit/Claude-Red | 7,914 | a8de813 | 739512a |
| SawyerHood/dev-browser | 6,690 | e5d746f | a25e767 |

I searched GitHub again for the most-starred skill repos. The same 8 are still the top
repos that ship skills; the others near the top (travisvn and BehiSecc's
awesome-claude-skills) are link lists with no SKILL.md files of their own, so the set is
unchanged and the numbers are comparable.

Then `stb lint --format json --no-plugins <dirs>` for each one, for the top 3 and top 5
by stars, and once with all of them together.
[`scripts/state_of_skills.py`](../scripts/state_of_skills.py) does all of it and prints
the raw numbers as JSON.
Some things to keep in mind:

- `stb` skips dot-folders. alirezarezvani/claude-skills keeps per-agent mirrors in
  `.gemini/`, `.codex/` and so on, so those aren't counted. 14 of its skills also exist
  twice outside the dot-folders. On 2026-10-23 that's 16 names: 15 identical copies
  (plugin layout plus a flat `skills/` folder) and one, `handoff`, that differs. They're
  counted twice below.
- awesome-claude-skills is mostly a list, but it also ships real skills: 32 hand-written
  ones at the top level and 832 generated Composio toolkit skills in `composio-skills/`.
  The two halves look very different, so I split them where it matters.
- "Description chars" is name + description summed over the pack. That's what counts
  against the listing budget.
- "Missing when" means the description never says when to use the skill (no "use when",
  "use for", "whenever", "triggers on" and similar). It's a regex, so read it as a hint.
- "Overlapping pairs" is TF-IDF cosine ≥ 0.35 between two descriptions. It's lexical. It
  catches obvious collisions, misses paraphrases, and sometimes flags pairs that are
  meant to sit next to each other.
- "Broken refs" only counts markdown links to relative files that don't exist. Bare
  paths in prose (often examples, like `scripts/tool.sh` in a guide about writing skills)
  aren't counted.
- "Spec errors" are `stb` errors other than the budget, broken refs and duplicate names,
  i.e. hard failures against the
  [Agent Skills spec](https://agentskills.io/specification): missing frontmatter, a name
  that isn't lowercase-hyphen, a description over 1024 chars.

Running this turned up four false positives in `stb`, which are fixed now: links inside
code blocks and inline code, placeholder links like `[Title](URL)`, "Use during ..." not
counting as a when-clause, and a hang on symlink loops.

## Per repo

| repo | skills | description chars | missing "when" | overlapping pairs | broken refs | bodies > 500 lines | spec errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| obra/superpowers | 15 | 2,630 | 0% | 1 | 0 | 0 | 0 |
| anthropics/skills | 20 | 9,696 | 10% | 1 | 0 | 1 | 1 |
| ComposioHQ/awesome-claude-skills (top level) | 32 | 8,306 | 50% | 2 | 0 | 2 | 0 |
| ComposioHQ/awesome-claude-skills (`composio-skills/`) | 832 | 103,384 | 100% | 1,862 | 0 | 0 | 92 |
| alirezarezvani/claude-skills | 397 | 189,059 | 0% | 58 | 2 | 3 | 0 |
| nidhinjs/prompt-master | 1 | 346 | 0% | 0 | 0 | 0 | 0 |
| Jeffallan/claude-skills | 67 | 30,376 | 0% | 2 | 0 | 0 | 0 |
| SnailSploit/Claude-Red | 79 | 43,758 | 18% | 1 | 2 | 41 | 46 |
| SawyerHood/dev-browser | 1 | 436 | 0% | 0 | 0 | 0 | 0 |

Errors and warnings by rule for every row, and for the combined installs, are in the
script's JSON output.

Notes per repo:

- **obra/superpowers** is the cleanest of the big ones. 15 short descriptions, all with a
  clear trigger. Its two long bodies from the first run are now under 500 lines. The one overlap is `executing-plans` / `subagent-driven-development`,
  two ways to run a plan, so some overlap is expected there.
- **anthropics/skills**: `claude-api` has a 1,068-char description, a bit over the
  spec's 1,024, and that looks deliberate (it's a detailed TRIGGER/SKIP block).
  `theme-factory` and `webapp-testing` describe what they do but not when to use them.
- **ComposioHQ top level**: half the descriptions have no when-clause. Several of these
  skills are copies of anthropics/skills (see below).
- **ComposioHQ `composio-skills/`**: these are generated, so one template fix fixes all
  of them. 92 have names like `Apify Automation` (spaces and capitals) or start with a
  hyphen (`-21risk-automation`), which the spec doesn't allow. None of the descriptions
  say when to use the skill. Some toolkits show up twice under two spellings, e.g.
  `SurveyMonkey Automation` and `survey_monkey-automation`.
- **alirezarezvani/claude-skills** is huge (397 skills, 189k description chars, about
  12.6x the budget on its own), but
  every description has a when-clause, which is good discipline at that size. Two links
  are still written relative to the repo root instead of the file, so they 404 even on GitHub.
- **Jeffallan/claude-skills** is clean apart from size: 67 skills, about 2x the budget
  on its own.
- **SnailSploit/Claude-Red**: about 2.9x the budget on its own. 28 SKILL.md files have no YAML frontmatter at all, so an
  agent can't list them. 18 descriptions are over 1,024 chars, and 41 bodies are over
  500 lines.
- The two single-skill repos are fine. prompt-master gets a name/folder mismatch, but
  only because of the folder I cloned into, so I left it out.

## The worst overlaps

These are the pairs most likely to compete for the same prompt, across all 8 repos
installed together. The generated Composio toolkit pairs are left out (more on those
below).

| score | pair | why |
|---:|---|---|
| 1.00 | `artifacts-builder` (Composio) / `web-artifacts-builder` (anthropics) | same description, renamed |
| 0.74 | `connect` / `connect-apps` (both Composio) | two entry points for the same thing |
| 0.68 | `java-architect` / `spring-boot-engineer` (Jeffallan) | Spring Boot, JPA, WebFlux in both |
| 0.61 | `dev-browser` (SawyerHood) / `browser-automation` (alirezarezvani) | browse, fill, screenshot |
| 0.60 | `internal-comms` (anthropics) / `team-communications` (alirezarezvani) | internal updates and reports |
| 0.58 | `general-counsel-advisor` / `gc-review` (alirezarezvani) | advisor and its review command |
| 0.56 | `generate` / `pw-init` (alirezarezvani, playwright-pro) | Playwright e2e setup |
| 0.52 | `chief-data-officer-advisor` / `cdo-review` (alirezarezvani) | same pattern as the GC pair |
| 0.52 | `architecture-designer` (Jeffallan) / `senior-architect` (alirezarezvani) | ADRs, diagrams, scalability |
| 0.51 | `form-cro` / `signup-flow-cro` (alirezarezvani) | signup form friction |

Within one pack, a pair like `gc-review` + `general-counsel-advisor` may be intentional
(a slash command next to its advisor). The usual fix is still the same: one sentence in
each description saying when to pick it over the other.

The generated Composio skills have the highest raw overlap count (1,862 pairs). Top
scorers are `Clockify` / `Toggl` (0.76) and `Harvest` / `Toggl` (0.58). Each one is a
different product, but the shared template ("Automate ... tasks via Rube MCP (Composio)")
makes them look alike to a lexical check. Putting the product name first and moving the
template text out of the description would remove most of that.

Rechecked on 2026-10-23: the top 10 are the same pairs with the same scores. One new
pair sits just below them, `cs-onboard` / `onboard` (alirezarezvani, 0.52).

## Installing the top 3 and top 5 together

Claude Code lists skill descriptions within a budget. Skills past it are silently left
out of the list the model sees. The figure people use is about 15,000 characters. That
number comes from a blog post
([fsck.com, Dec 2025](https://blog.fsck.com/2025/12/17/claude-code-skills-not-triggering/)),
not from Anthropic's source or docs, and it may have changed since. Treat everything
below as relative, not exact.

Top 3 by stars: obra/superpowers, anthropics/skills, ComposioHQ/awesome-claude-skills.

| install | skills | description chars | vs ~15k |
|---|---:|---:|---:|
| superpowers + anthropics | 35 | 12,326 | 82%, fits |
| + Composio top level only (top 3) | 67 | 20,632 | 138% |
| + all of Composio | 899 | 124,016 | about 8.3x |
| top 5, Composio top level only (+ alirezarezvani, prompt-master) | 465 | 210,037 | 14x |
| top 5, all of Composio | 1,297 | 313,421 | about 21x |

The headline 138% counts Composio's 32 hand-written skills only, not the 832 generated
ones in `composio-skills/`. Counting those too is the "all of Composio" row.

- superpowers and anthropics/skills fit together with some room left. Most people
  probably have this setup.
- Adding Composio's hand-written skills goes over the budget. It also adds **13 name
  clashes**, because Composio ships its own copies of `docx`, `pdf`, `pptx`, `xlsx`,
  `skill-creator`, `mcp-builder`, `canvas-design` and others. Six are byte-identical
  to anthropics/skills. The other seven have drifted, so you get two different skills with the same
  name and the agent can only pick one.
- Adding all of `composio-skills/` puts the set at roughly 8x the budget. By `stb`'s
  count, about 848 of 899 descriptions would never be shown.
- The top 5 is mostly alirezarezvani: that one pack is 189k chars, so adding it takes the
  set to 14x even without the generated Composio skills, with 30 duplicate names and
  roughly 420 of 465 descriptions past the budget.

For scale: all 8 repos together are 1,444 skills and 387,991 description chars (about 26x). Nobody
should install that, but it shows how fast a few "install the whole pack" steps add up.

## What changed since the last run

Two weeks on (2026-10-09 to 2026-10-23), 7 of the 8 repos have new commits but the picture
is the same. The top 3 moved from 137% to 138% of the budget (+15 chars, all from
superpowers). alirezarezvani grew by 10 skills and 6k chars and now has 16 duplicated names
instead of 14. superpowers no longer has bodies over 500 lines. SnailSploit's
missing-"when" share went from 27% to 18%. Composio hasn't changed. The method is the
same; the only additions are the top-5 rows, star counts, and a script so the run can be
repeated. `stb` gained one rule in between (`: ` in unquoted frontmatter values when PyYAML
isn't installed), and lint ran here without PyYAML.

## What would help

None of this needs a rewrite:

- **Packs with generated skills**: fix the template once (spec-valid names, a "Use when
  ..." clause, the product name up front).
- **Mega-packs**: say in the README that the pack is meant to be installed per category,
  not all at once. alirezarezvani and Jeffallan already split into plugins, so this is
  mostly documentation.
- **Packs that vendor other packs' skills**: rename them, or drop them and link to the
  source, so users don't end up with two `pdf` skills.
- **Everyone**: run a linter in CI. `stb lint --format json` works, and so do
  `/skill-doctor` and `claude plugin eval` if you're Claude-only.

To reproduce: shallow-clone the repos at the commits above into one folder as
`<owner>_<repo>` and run `python scripts/state_of_skills.py <folder>` from the repo root.
