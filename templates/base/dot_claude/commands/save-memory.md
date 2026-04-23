---
description: Save a fact to project memory for future sessions
argument-hint: "<fact to remember>"
allowed-tools: Read Write Glob
---

Save this to project memory: $ARGUMENTS

Follow the memory convention in `.claude/memory/README.md`:

1. Decide the memory type (user / feedback / project / reference)
2. Choose a descriptive filename (e.g., `feedback_testing.md`, `project_deadline.md`)
3. Check if an existing memory file already covers this — update it instead of duplicating
4. Write the file with proper frontmatter (name, description, type)
5. Add a one-line entry to `.claude/memory/MEMORY.md`

For feedback/project types, structure the body as: rule/fact, then **Why:** and **How to apply:** lines.
