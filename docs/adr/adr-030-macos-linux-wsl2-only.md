# ADR-030: macOS and Linux only; Windows through WSL2; a native Windows shell is refused

- Status: Accepted
- Date: 2026-09-30
- Implements: [#1070](https://github.com/VytCepas/project-init/issues/1070)
- Relates to: [harbor#831](https://github.com/VytCepas/harbor/issues/831) (the cross-repo
  epic) and harbor's `CONTRACTS/platforms.md` (the shared contract)
- Supersedes in part: [ADR-027](adr-027-claude-config-projection.md), its Windows rationale only

## Context

PI-463 made native Windows a supported target: hooks ran through Git Bash, a
`windows-portability` CI job exercised them on `windows-latest`, and the
scaffolded `conftest.py`, `prod_guard.py` and `tools/box_install.py` carried
Windows-only branches. ADR-027 cited native-Windows users as one of two reasons
the committed `.claude/` projection must be plain files rather than a symlink.

The operator decided on 2026-09-30 (harbor#831) that every solution runs on
macOS and Linux, and on Windows only inside WSL2. It reverses harbor#615.

## Decision

- **Supported: macOS and Linux.** WSL2 is Linux and is supported on the same
  terms, working inside the WSL filesystem.
- **A native Windows shell is refused**, naming WSL2, before anything runs:
  `uname -s` starting with `MINGW`, `MSYS` or `CYGWIN`, or Python's
  `platform.system()` being `Windows`. The refusal sits at every entry point
  this repo ships: `install.sh`, the `project-init` CLI (scaffold, upgrade and
  every other subcommand) and the scaffolded SessionStart hook
  (`session_setup.sh`, exit 2).
- **The Windows-only code goes:** the `windows-portability` CI job, the
  USERPROFILE/HOMEDRIVE/HOMEPATH/APPDATA/LOCALAPPDATA redirect in the
  scaffolded `conftest.py`, `prod_guard.py`'s off-POSIX branch, and
  `box_install.py`'s `os.name == "nt"` and copied-entrypoint branches.

## What this supersedes in ADR-027

ADR-027's "Claude Code now runs natively on Windows (no WSL), so those users are
real", and its claim that plain files matter because they restore "on Linux,
macOS and Windows", no longer carry weight: native Windows is refused. **The
projection itself does not change.** ADR-027's macOS reason stands on its own:
`core.symlinks=false` is the macOS default too, so a committed symlink still
checks out as a text file there. Whether the projection should change is a
separate decision this ADR does not take.

## Consequences

- A Windows user without WSL2 is told how to get in, instead of meeting a hook
  that loads on an unproved platform and fails to match.
- `project-init upgrade` rewrites a scaffolded repo's `conftest.py` without the
  Windows variables, and its SessionStart hook gains the refusal.
- Nothing in CI proves Git Bash any more, which is the point: it is no longer a
  target.
