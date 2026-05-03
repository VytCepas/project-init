# Preset Configuration Guide

## Overview

Presets are TOML configurations that customize the scaffolder behavior for different project types.

## Available Presets

### Minimal

Bare-bones Claude Code setup with basic `.claude/` infrastructure.

### Obsidian

Includes Obsidian vault configuration and note-taking setup.

### Obsidian + LightRAG

Adds LightRAG memory stack integration for agent cross-project memory.

## Preset Structure

```toml
[preset]
name = "preset-name"
description = "What this preset does"

[preset.template-layers]
base = true
obsidian = true  # optional
lightrag = true  # optional

[preset.customizations]
# Custom variables and substitutions
project_name = "My Project"
```

## Customizing Presets

Edit `templates/presets/*.toml` to:
- Enable/disable template layers
- Set default variable values
- Define custom file substitutions

## Creating a New Preset

1. Add a new `.toml` file in `templates/presets/`
2. Define layers and customizations
3. Update preset list in wizard
4. Add tests in `tests/test_presets.py`
