# Implementation Guide

## Getting Started

This guide covers how to contribute to the project and implement new features.

## Development Setup

1. Clone the repository
2. Run `uv sync` to install dependencies
3. Run `uv run pytest` to verify the test suite

## Project Structure

- `src/` — Main Python source code
- `templates/` — Scaffolder templates for output projects
- `tests/` — Pytest test modules
- `.claude/` — Claude Code infrastructure

## Development Workflow

1. Create a GitHub Issue describing the work
2. Create a feature branch: `git checkout -b feature/PI-<n>-<slug>`
3. Make changes and test locally
4. Push and create a draft PR
5. Wait for CI to pass
6. Mark ready for review and merge

## Testing

Run tests with coverage:
```bash
uv run pytest --cov=src tests/
```

Tests are organized by behavior area:
- `test_*.py` — Focused tests for specific features
- Each template change has corresponding tests

## Code Standards

- Use `ruff` for linting (no black/isort/mypy)
- Follow existing code patterns
- Keep the scaffolder small and deterministic
- Avoid external dependencies beyond tomllib and argparse

## Documentation

- Update README.md for user-facing changes
- Update CLAUDE.md for agent/developer instructions
- Keep skill documentation in `.claude/skills/*/SKILL.md`

## Questions?

- Check CLAUDE.md for agent guidelines
- Review existing issues for context
- Ask in GitHub Discussions
