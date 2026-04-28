# `.claude/scripts/`

Helper scripts invoked by the user, by hooks, or by agents via the Bash tool. Prefer bash or python stdlib. Document each script with a one-line header comment.

## Available scripts

- **`install-hooks.sh`** — Symlink or copy git hooks from `.github/hooks/` to `.git/hooks/`
- **`create-issue.sh`** — Create a typed GitHub issue and print its issue number
- **`start-issue.sh`** — Create an issue branch, push it, and open a draft PR
- **`promote-review.sh`** — Mark a draft PR ready for review
- **`monitor-pr.sh`** — Poll PR checks and optionally squash-merge with `--merge`
- **`push-branch.sh`** — Push current branch with retry and remote-SHA verification (handles transient 5xx errors)
