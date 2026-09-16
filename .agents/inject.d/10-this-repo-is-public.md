---
id: project-init-is-a-public-repo
event: SessionStart
when: always
once: never
---

**This repository is PUBLIC on GitHub — a commit, an issue and a PR body all
publish.** Most other trees on this box are private, so the habits that are safe
there are not safe here.

Never publish, in code or in issue/PR/commit text: a client or account name, a
person's or role's email address, an absolute filesystem path from this machine,
or content from an agent's private configuration directory. **A template is
generic by construction** — the moment one carries a real customer or a real
account it stops being a template and becomes a disclosure.

**The exception is this package's own published metadata.** `pyproject.toml`'s
`authors` field carries the maintainer's name and email deliberately, because
PyPI requires it. That is published ON PURPOSE and must not be "fixed". The test
is whether a fact is already public by intent, not whether it is on disk — and
`git grep` over tracked files is how you check, because an untracked scratch file
is not the risk and a tracked one is.

**This file is itself published**, which is why it names categories rather than
the real names: the private box tier holds the list, and a warning that
enumerated what it protects would leak it on the first commit.

**It loads at session start rather than on the command that publishes.** It fired
on `cmd-contains git` AND `cmd-contains commit` first — `when` repeats are ANDed
— so it was silent for `gh issue create` and `gh pr create`, and the documented
workflow opens an issue *before* the first commit. The warning arrived after the
publish it existed to prevent, and there is no OR in the predicate vocabulary.

A pack under `.claude/` is loaded by Claude and by nothing else, so this rule
belongs in `AGENTS.md` as well — the file every agent surface reads. Until it is
there, this pack is the only copy and that is a known gap, not the design.
