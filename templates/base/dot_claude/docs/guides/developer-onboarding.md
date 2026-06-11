# Developer onboarding — personal machine setup

This page covers **per-developer machine state** that the scaffolder
deliberately does not manage: global git configuration and editor sync are
personal, not repository state, so they are documented here instead of being
scaffolded (see the project-init decision in PI-140).

Everything repo-level (linting, commands, env examples) ships with the
repository. The one per-clone step: run `.claude/scripts/install_hooks.sh`
once to activate the `pre-commit` (gitleaks secret scan), `commit-msg`,
and `pre-push` git hooks — git does not enable repository hooks
automatically. Install [gitleaks](https://github.com/gitleaks/gitleaks#installing)
for fast local secret scanning; without it the pre-commit scan is skipped
and CI catches leaks instead.

## Dependency updates (Renovate)

The repo ships a `renovate.json` (weekly grouped updates, GitHub Actions
pinned by digest, lockfile maintenance — managers activate automatically
from the files present). Renovate PRs arrive as `[nojira][chore] …`, which
the PR validators accept. One per-org step: install the
[Renovate GitHub App](https://github.com/apps/renovate) on the repository.

To centralize policy across an organization, replace the `extends` list
with a shared preset and keep repo files minimal:

```json
{ "extends": ["github>your-org/renovate-config"] }
```

## Global gitignore

Keep OS and editor junk out of every repo you touch, without bloating each
project's `.gitignore`:

```bash
git config --global core.excludesFile ~/.gitignore_global
cat >> ~/.gitignore_global <<'EOF'
.DS_Store
Thumbs.db
*.swp
.idea/
EOF
```

Project `.gitignore` files stay focused on project artifacts (build output,
env files, caches) — never add personal editor noise to them.

## Recommended global git config

```bash
git config --global init.defaultBranch main
git config --global pull.rebase true          # no accidental merge commits on pull
git config --global push.autoSetupRemote true # first push sets upstream
git config --global fetch.prune true          # drop deleted remote branches
```

Identity (use your work email on work machines):

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

## Commit signing (if your org requires it)

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
```

## Editor settings

- **VS Code Settings Sync** is an account-level feature — enable it in VS Code
  itself (`Settings Sync: Turn On`). It is intentionally not configured by the
  repository.
- Repo-level editor settings (format-on-save, recommended extensions) live in
  the repository's `.vscode/` directory when the project opted into that
  overlay — personal themes and keybindings never belong there.

## Checklist

- [ ] Global gitignore configured
- [ ] Global git config applied (rebase pulls, pruning, identity)
- [ ] Commit signing set up, if required
- [ ] Repo hooks installed: run `.claude/scripts/install_hooks.sh` once per clone
- [ ] gitleaks installed for the local pre-commit secret scan
