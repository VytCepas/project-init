# ADR-011: Publish to PyPI via trusted publishing; supersedes ADR-008's deferral

- Status: Accepted
- Date: 2026-06-12
- Supersedes: ADR-008 (in part — git distribution stays supported)
- Implements: #169

## Context

ADR-008 chose git-only distribution and deferred PyPI over two costs:
API-token custody and mandatory version discipline. Both have since been
eliminated:

- **Trusted publishing** authenticates the GitHub Actions workflow to PyPI
  directly via OIDC — there is no token to create, store, rotate, or leak.
- **Release discipline already exists**: PI-144 introduced tag-triggered
  releases with a version-match gate and a Conventional-Commits changelog.

Meanwhile the `project-init` name was confirmed free on PyPI (checked
2026-06-12 against both the JSON API and the simple index). A naming review
considered rebranding (pamatas, formwork, agent-scaffold); the owner chose
to keep `project-init` — claiming the name also defends it.

## Decision Outcome

Publish every tagged release to PyPI from the existing `release.yml` via a
`publish-pypi` job:

- Runs only after the GitHub Release job succeeds (`needs: release`).
- Authenticates via OIDC (`id-token: write`) against the `pypi`
  environment — protection rules can be added on the environment later.
- Uses `pypa/gh-action-pypi-publish` (the canonical action; `release/v1`
  per its own guidance, digest-pinned by Renovate like every other action).

Install paths after this lands, in recommendation order:

1. `uv tool install project-init` / `uvx project-init` (PyPI)
2. `curl … install.sh | bash` (git, release-pinned — unchanged)
3. `uv tool install git+https://github.com/VytCepas/project-init@vX.Y.Z`

## One-time manual step (owner)

Before the first publish, register the *pending publisher* on pypi.org
(Account → Publishing): project `project-init`, owner `VytCepas`,
repository `project-init`, workflow `release.yml`, environment `pypi`.
The first tagged release after that claims the name.

## Consequences

- Anyone can install without trusting a curl-pipe-bash script.
- The wheel already bundles `templates/` (hatch force-include), so PyPI
  installs are fully functional — verified by the existing wheel-smoke CI
  job.
- Version bumps remain manual in two places (pyproject + `__init__.py`);
  the release workflow's version-match gate keeps tags honest.
