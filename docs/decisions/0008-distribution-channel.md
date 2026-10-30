# ADR-008: Distribution stays git-based with tagged releases; PyPI deferred

- Status: Superseded in part by ADR-011 (PyPI publishing added; git channel unchanged)
- Date: 2026-06-11
- Implements: distribution decision required by #144

## Context

`install.sh` cloned `main` and the documented update path was `git pull` —
every user tracked an unreleased moving target, and version 0.1.0 was never
followed by a tag. For colleagues to adopt project-init safely, installs
must be reproducible and pinnable. The open question was the channel:
git-only, or also publish to PyPI.

## Considered Options

1. **Git-only with tagged releases** — release workflow on tag push,
   `install.sh` resolves the latest release tag, `PROJECT_INIT_REF` pins.
2. **Also publish to PyPI** — `uv tool install project-init`.

## Decision Outcome

Chosen option 1, git-only with tagged releases:

- Pinning works without PyPI: `install.sh` defaults to the latest GitHub
  Release tag; `PROJECT_INIT_REF=vX.Y.Z` pins a version and
  `PROJECT_INIT_REF=main` opts into the development head. Direct installs
  work too: `uv tool install git+https://github.com/VytCepas/project-init@vX.Y.Z`.
- PyPI adds real overhead (account/token custody, name claim, mandatory
  version discipline for every fix) and its main benefit — frictionless org
  rollout — has no current demand.
- The decision is cheap to reverse: a `uv publish` step appended to the
  existing release workflow is the entire migration.

**Revisit trigger:** an org rollout that needs `uv tool install
project-init` from an index (private mirrors, locked-down egress), or a
second team adopting the tool.

### Consequences

- Good: reproducible installs now; no new infrastructure or secrets.
- Good: the release workflow (wheel + git-cliff changelog from
  Conventional Commits, ADR-006) is the single release path.
- Bad: install still requires git + GitHub reachability; air-gapped
  environments must mirror the repo.
