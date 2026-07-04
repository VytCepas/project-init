# Contributing

The canonical, always-current guide lives in the repo root:
**[CONTRIBUTING.md](https://github.com/VytCepas/project-init/blob/main/CONTRIBUTING.md)**.
This page is intentionally a stub so the two can never drift apart.

The 30-second version:

```bash
git clone https://github.com/VytCepas/project-init.git
cd project-init
just setup     # uv sync + dev deps + pre-push CI gate
just ci        # lint + full test suite — must be green before a PR
```

- The `justfile` is the command surface (`just --list`); `uv` for everything,
  `ruff` only.
- Branches: `type/PI-<n>-slug` for issue-linked work; PR titles use
  Conventional Commits (`type(PI-N): description`, or `type: description`
  with no issue).
- Any change under `templates/` needs a matching test in the focused
  `tests/<layer>/test_*.py` module — templates are tested by scaffolding
  into a temp dir.
