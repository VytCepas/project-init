<!--
PR title must use Conventional Commits and becomes the squash-merge commit message:
  - issue-linked work: `type(PI-N): description`  e.g. `feat(PI-42): add new overlay`
  - no-issue minor fix: `type: description`        e.g. `fix: handle empty preset name`
-->

## What & why

<!-- What does this change do, and why is it needed? -->

## Related issue

Closes #
<!-- Omit this line for minor fixes without a tracking issue. -->

## Checklist

- [ ] `just ci` passes locally (lint + full test suite)
- [ ] Changes under `templates/` have a matching test in `tests/<layer>/test_*.py`
- [ ] Docs / README updated if behavior or flags changed
- [ ] PR title follows Conventional Commits (`type(PI-N): description`, or `type: description` with no issue)
