#!/usr/bin/env bash
# post_edit_lint.sh: the old name of post-edit-lint.sh, kept until 2026-12-01 so that a tool
# or a note that still names this path keeps working. Run post-edit-lint.sh.
exec "$(dirname "$0")/post-edit-lint.sh" "$@"
