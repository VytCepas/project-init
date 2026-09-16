# AGENTS.md

Canonical instructions for this repository live in [CLAUDE.md](CLAUDE.md).

Read [CLAUDE.md](CLAUDE.md) before working in this codebase. It is the source of truth for repo conventions, testing rules, GitHub workflow, and branch naming.

## This repository is PUBLIC

A commit, an issue and a PR body all publish. Most other trees on this machine
are private, so the habits that are safe there are not safe here.

Never publish, in code or in issue/PR/commit text: a client or account name, a
person's or role's email address, an absolute filesystem path from this machine,
or content from an agent's private configuration directory. A template is generic
by construction — the moment one carries a real customer or a real account it
stops being a template and becomes a disclosure.

**The exception is this package's own published metadata.** `pyproject.toml`'s
`authors` field carries the maintainer's name and email deliberately, because
PyPI requires it. That is published on purpose and must not be "fixed". The test
is whether a fact is already public **by intent**, not whether it is on disk —
and `git grep` over tracked files is how you check, because an untracked scratch
file is not the risk and a tracked one is.

This rule lives here because `AGENTS.md` is the file every agent surface reads.
The same text is delivered at session start by
[`.claude/inject.d/10-this-repo-is-public.md`](.claude/inject.d/10-this-repo-is-public.md),
which Claude loads and nothing else does — so the pack is the convenience and
this section is the canonical copy.

## Skills (load on demand)

Before any GitHub action (create issue, branch, push, PR, merge), check [`.agents/skills/INDEX.md`](.agents/skills/INDEX.md) and load the relevant skill. Do not read all skills upfront — load only the one that matches what you are about to do.
