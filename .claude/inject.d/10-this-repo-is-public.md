---
id: project-init-is-a-public-repo
event: PreToolUse
tool: Bash
when: cmd-contains git
when: cmd-contains commit
once: match
---

**This repository is PUBLIC on GitHub.** Measured 2026-09-15 with
`gh repo view --json visibility`. Almost every other tree on this box is private,
so the habits that are safe there are not safe here: this is one of only two
repositories where a commit publishes.

Never commit, and never put in an issue, a PR body or a commit message: a client
or account name, any person's or role's email address, an absolute `/Users/...`
path, or content from the assistant's private configuration directory. A template
is generic by construction — the moment one carries a real customer or a real
account it stops being a template and becomes a disclosure.

**This file is itself published**, which is why it describes the categories
rather than listing the real names: the private box tier holds the list, and a
warning that enumerates what it is protecting would leak it on the first commit.

Ask what is PUBLISHED, not what is on disk — `git grep` over tracked files is the
check, because an untracked scratch file is not the risk and a tracked one is.
Verified clean on 2026-09-15.
