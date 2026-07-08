#!/bin/bash
# Thin shim — actual logic lives in the sibling ../hooks/dag_workflow.py
# (canonical: .agents/hooks/; the same tree is mirrored under .claude/ for
# Claude Code). Resolving relative to $0 keeps whichever copy is invoked working.
exec python3 "$(dirname "$0")/../hooks/dag_workflow.py" push "$@"
