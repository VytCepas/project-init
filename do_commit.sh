#!/bin/bash
cd ~/projects/project_init
git add -A
git commit -m "fix(PI-606): Restore plugins directory and rename plugin metadata to .agents-plugin"
.agents/scripts/push_branch.sh
