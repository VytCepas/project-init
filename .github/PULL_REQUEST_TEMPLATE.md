<!--
PR title must use Conventional Commits: `type: description`
e.g. `fix: handle empty preset name` or `feat(PI-42): add new overlay`.
It becomes the squash-merge commit message.
-->

## What & why

<!-- What does this change do, and why is it needed? -->

## Related issue

Closes #
<!-- Omit this line for minor fixes without a tracking issue. -->

## Checklist

- [ ] `just ci` passes locally (lint + full test suite)
- [ ] Changes under `templates/` have a matching test in `tests/test_*.py`
- [ ] Docs / README updated if behavior or flags changed
- [ ] PR title follows Conventional Commits (`type: description`)
