---
name: test-driven-development
description: >-
  Guides test-first and test-backed changes using pytest: unit tests with
  mocked or stubbed external I/O, clear boundaries between unit and integration
  tests, and fast feedback loops. Use when adding features, fixing bugs,
  hardening CSV/config validation, or when the user mentions TDD, pytest,
  mocks, fixtures, regression tests, or CI.
---

# Test-driven development (project skill)

## When to read this skill

Use it whenever behavior is **non-trivial**, **easy to regress**, or **touches external systems** (databases, filesystem, network). Prefer **tests that fail first** (or at least a failing reproduction) before locking in implementation.

## Defaults for this repository

1. **Unit tests are the default**
   - Run: `pytest` from the repo root (or `python -m pytest tests/ -q`).
   - **No real sockets** in the default unit suite: use stubs/fakes for importer registries (see `tests/test_runner_registry.py`).

2. **Integration tests are optional and explicit**
   - Anything requiring `docker compose` or live credentials belongs behind markers or a separate folder/name convention—do not make the default `pytest` run depend on Docker.

3. **What to test first (high value)**

   - **Config**: invalid schema keys, missing files, happy path minimal config (`tests/test_config_parser.py`).
   - **Filters / materialization**: pure functions—table-driven cases, edge strings, empty rows.
   - **Validation / dry-run**: orchestration decisions without connecting to DBs (`tests/test_validation_dry_run.py`).
   - **Runner**: injected importer registry executes selected backends and propagates failures predictably.

## TDD loop (recommended)

1. **Red**: write a failing test that expresses desired behavior (assertion or expected exception).
2. **Green**: implement the smallest change to pass.
3. **Refactor**: clean up while keeping tests green; avoid drive-by unrelated refactors.

If the user did not ask for strict TDD, still keep the **“failing test → fix → refactor”** discipline for bug fixes.

## Mocking guidelines

- **Mock at boundaries**: filesystem and DB clients, not every private helper.
- **Prefer fakes over deep mocks** when a small in-memory fake/registry is clearer.
- **Avoid** testing implementation details (exact call order of internal private methods) unless it is a real contract.

## pytest conventions here

- Keep tests **fast** and **deterministic** (no wall-clock sleeps unless unavoidable).
- Use **`tmp_path`** for file-based tests when needed.
- Prefer explicit `pytest.raises(...)` for error semantics.

## Anti-patterns

- Tests that require manual Docker startup for `pytest` to pass locally.
- Tests that hit production-like endpoints or shared developer databases.
- Giant fixtures that obscure what a single test is asserting.

## Related project docs

- `docs/ARCHITECTURE.md` — how unit vs integration testing is intended to coexist.
