# Build Reproducibility

This audit covers the CI and build-environment surfaces used by `project-init`
itself.

## Findings

- Docker images: no Dockerfiles or container images are used by the project.
- Python dependencies: `pyproject.toml` keeps normal package constraints, while
  `uv.lock` is tracked for exact CI/dev resolution.
- GitHub Actions runners: workflows use `ubuntu-24.04` instead of
  `ubuntu-latest`.
- uv setup: workflows pin the uv installer to `0.11.7`.
- Docs build: MkDocs dependencies are installed through the `docs` extra and
  resolved from `uv.lock`; the docs workflow no longer performs an unpinned
  `pip install`.
- Pre-commit hooks: generated hooks depend on local tools (`uv`, `ruff`, and
  `python3`) and do not download packages at hook runtime.

## Maintenance

When updating dependency constraints or the pinned uv version, update
`uv.lock`, run the local checks, and keep generated workflow templates aligned
with the root project workflows where the behavior is shared.
