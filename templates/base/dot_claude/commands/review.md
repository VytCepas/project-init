---
description: Review staged or recent changes for bugs, style issues, and missed edge cases
argument-hint: "[commit-range or file]"
allowed-tools: Bash Read Grep Glob
---

Review the code changes specified by: $ARGUMENTS

If no argument given, review all staged changes (`git diff --cached`). If nothing is staged, review the last commit.

Focus on:
- **Bugs** — logic errors, off-by-ones, null/undefined risks
- **Security** — injection, auth issues, secret exposure
- **Style** — naming, dead code, overly complex logic
- **Edge cases** — empty inputs, concurrency, error paths

Be specific: cite file:line, quote the problematic code, suggest a fix. Skip nitpicks.
