#!/bin/bash
# Auto-commit hook: triggered after TaskUpdate
# Reads hook stdin JSON, checks if task was marked completed, then commits and pushes.

INPUT=$(cat)

# Extract task status from tool_input
STATUS=$(echo "$INPUT" | jq -r '.tool_input.status // empty')

# Only commit when a task is marked as completed
if [ "$STATUS" != "completed" ]; then
  exit 0
fi

# Extract task description for commit message
TASK_DESC=$(echo "$INPUT" | jq -r '.tool_input.description // .tool_input.task_id // "task completed"')

cd /Users/1ar/git/Recast || exit 0

# Check if there are any changes to commit
if git diff --quiet HEAD && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  exit 0
fi

# Stage all changes
git add -A

# Commit with task description
git commit -m "$(cat <<EOF
auto: ${TASK_DESC}

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)" 2>/dev/null || exit 0

# Push to remote
git push 2>/dev/null || true
