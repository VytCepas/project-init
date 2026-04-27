# `.claude/scripts/`

Helper scripts invoked by the user, by hooks, or by agents via the Bash tool. Prefer bash or python stdlib. Document each script with a one-line header comment.

## Available scripts

- **`install-hooks.sh`** — Symlink or copy git hooks from `.github/hooks/` to `.git/hooks/`
- **`monitor-pr.sh`** — Monitor a PR for test completion and review status (1-min checks, max 5 retries)
