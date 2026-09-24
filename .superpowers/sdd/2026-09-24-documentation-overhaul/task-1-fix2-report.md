# Task 1 fix2 report

## Status

Implemented the three requested scoped corrections.

- Restored concise README boundary material for the interactive CLI, OpenAI-compatible providers, and Web login/realtime TTS behavior while leaving future topic documents as the navigation target.
- Corrected the getting-started project layout statement: projects are initially saved under `stories/<project_id>/`, then `ProjectManager` renames them to date/title directories after script generation.
- Corrected the state description: `generating_audio` is not a normal CLI-persisted audio-generation state; Web cancellation persists it for resume.

## Checks

- `git diff --check` — passed.
- Markdown link/reference scan with `rg` — passed for the changed entry-point files.
- Stale-claim scan — no matching stale claims.
- `.venv/bin/python -m pytest tests/e2e/test_cli.py tests/e2e/test_pipeline.py -q` — not runnable; `.venv/bin/python` is absent.
- `python3 -m pytest tests/e2e/test_cli.py tests/e2e/test_pipeline.py -q` — not runnable; system Python 3.14 has no `pytest` module.

## Concerns

The focused pytest suite was not executed because the worktree has no usable pytest environment. No source-code behavior was changed.
