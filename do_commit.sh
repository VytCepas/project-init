#!/bin/bash
cd ~/projects/project_init
git add -A
git commit -m "fix(PI-606): Add pre_edit_issue_guard to plugin hooks"
.agents/scripts/push_branch.sh
