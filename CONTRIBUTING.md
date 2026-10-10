# Contributing

Thanks for helping. `stb` is plain Python 3.10+ with no required dependencies. Please keep it that way.

## Run the checks

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
uvx ruff check . && uvx ruff format --check .
```

The tests never call a model, and new tests shouldn't either. Runner tests use recorded or hand-written transcripts in `tests/fixtures/`.

## Claiming an issue

Comment on the issue saying you'd like to take it, and I'll assign you. If there's no PR or update after a week or so, it goes back up for grabs. Issues labelled `good first issue` are small and say which files to touch.

## PR checklist

- [ ] tests and ruff pass locally
- [ ] new behaviour has a test
- [ ] new lint rule or flag has a line in the README
- [ ] fixtures contain no real names, paths, keys or emails
- [ ] the PR links the issue (`Fixes #12`)

Small PRs get merged faster. If you're unsure about an approach, ask in the issue first.
