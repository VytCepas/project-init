#!/bin/bash
# RETIRED: use gh pr checks --watch or arm auto-merge via start-issue.sh instead.
#
# To watch CI interactively:
#   gh pr checks --watch
#
# To auto-merge when CI passes (requires Allow auto-merge in repo settings):
#   gh pr merge <number> --auto --squash --delete-branch
#
# start-issue.sh arms auto-merge automatically at PR creation time.

echo "monitor-pr.sh is retired." >&2
echo "" >&2
echo "To watch CI:    gh pr checks --watch" >&2
echo "To auto-merge:  gh pr merge <n> --auto --squash --delete-branch" >&2
exit 1
