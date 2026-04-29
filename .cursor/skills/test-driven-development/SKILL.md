---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code. Guides the assistant to write tests first following the Red-Green-Refactor cycle.
---

# Test-Driven Development (TDD)

## The Red-Green-Refactor Cycle

1. **Red**: Write a failing test for the desired functionality. The test should fail because the feature isn't implemented yet.
2. **Green**: Write the minimum amount of code necessary to make the test pass. Do not over-engineer at this step.
3. **Refactor**: Clean up the code, remove duplication, and ensure it follows design standards while keeping the tests green.

## Instructions for the Assistant
- When asked to implement a feature, **always** write the unit tests first.
- Present the tests to the user or execute them (they will fail).
- Once the tests are in place, write the implementation code.
- Run the tests again to ensure they pass.
- Use `pytest` for Python projects.

## Mocking and Dependencies
- Mock external dependencies (like databases, APIs, or file systems) during unit tests.
- Only use real connections in integration or end-to-end tests.
- For `polyglot-import-csv`, mock the database connectors (Redis, Neo4j, Cassandra, etc.) when testing the JSON configuration parsing and CSV reading logic.
