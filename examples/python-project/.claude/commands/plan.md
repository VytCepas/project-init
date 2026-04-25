---
description: Plan a task test-first — write acceptance tests before the implementation plan
argument-hint: "<task description>"
allowed-tools: Read Grep Glob Bash
---

Plan the following task using test-driven development: $ARGUMENTS

## Phase 1 — Understand

Read relevant files, check existing patterns, scan `.claude/memory/MEMORY.md` for prior decisions. Do not write any code yet.

## Phase 2 — Write acceptance tests first

Write concrete, runnable test cases that the finished implementation must pass. These are real code (pytest / jest / etc.), not prose descriptions.

```python
# Example shape — replace with actual tests for this task
def test_<feature>_<scenario>():
    # arrange
    ...
    # act
    result = ...
    # assert
    assert result == expected
```

Rules:
- Tests must be **runnable today** (they will fail — that is correct)
- One assertion per test
- Name tests `test_<unit>_<scenario>` so failures are self-documenting
- Cover the happy path, at least one edge case, and one failure case

Commit these tests before writing any implementation. The test suite must be **red** before you start.

## Phase 3 — Implementation plan

Write a numbered step-by-step plan with file paths and approach for each step. Each step should map to one or more of the acceptance tests above.

## Phase 4 — Risks and scope

- What existing functionality could break?
- What is explicitly out of scope?
- Any ambiguities or decisions that need human input?

## Phase 5 — Definition of done

A checklist that references the acceptance tests. The task is complete when:
- [ ] All acceptance tests from Phase 2 pass
- [ ] Linter reports no errors (`uv run ruff check .`)
- [ ] No new test files left in a failing state

---

Output the full plan in markdown. **Do not write implementation code** until the user approves the plan and the acceptance tests are committed.
