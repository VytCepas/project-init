# `.claude/agents/`

Claude Code subagent definitions. Define custom subagent personas here when you need specialized agents for repeatable tasks (e.g., a code reviewer, a documentation specialist, a performance analyzer).

## How to create a subagent

1. Create a `.md` file with a frontmatter block:

```yaml
---
name: agent-name
description: What this agent does and when to invoke it
model: sonnet                    # optional: sonnet or opus
tools:                           # list of tools this agent can use
  - Read
  - Grep
  - Bash
maxTurns: 15                     # optional: max conversation depth
---

<Detailed instructions for the agent's behavior, role, and approach>
```

2. Name the file after the agent (e.g., `reviewer.md` for a `reviewer` agent)

3. Invoke the agent in skills or from the CLI using `Agent({"description": "...", "subagent_type": "agent-name", "prompt": "..."})`

## Reference

See the [Claude Code subagents documentation](https://docs.claude.com/en/docs/claude-code/sub-agents) for full details on agent capabilities, tool access, and context management.
