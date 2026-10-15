#!/usr/bin/env bash
# SessionStart hook: inject recent memories as startup context
# Reads the project memory directory and injects the 5 most recently modified
# memory files as additional context for the session.

# Find the project memory directory from Claude Code's project path
# Claude Code sets CLAUDE_PROJECT_DIR or we derive from cwd
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SAFE_PATH=$(echo "$PROJECT_DIR" | sed 's|/|-|g; s|^-||')
MEMORY_DIR="$HOME/.claude/projects/$SAFE_PATH/memory"

# Fall back: check if MEMORY.md exists in the detected path
if [ ! -d "$MEMORY_DIR" ]; then
    # Try the current working directory name
    SAFE_PATH=$(echo "$(pwd)" | sed 's|/|-|g; s|^-||')
    MEMORY_DIR="$HOME/.claude/projects/$SAFE_PATH/memory"
fi

[ ! -d "$MEMORY_DIR" ] && exit 0

# Find memory files with frontmatter (structured memories, not MEMORY.md)
MEMORY_FILES=$(find "$MEMORY_DIR" -maxdepth 1 -name "*.md" ! -name "MEMORY.md" \
    -newer "$MEMORY_DIR/MEMORY.md" -o -name "*.md" ! -name "MEMORY.md" 2>/dev/null | \
    head -20)

[ -z "$MEMORY_FILES" ] && exit 0

# Sort by modification time, take 5 most recent
RECENT=$(echo "$MEMORY_FILES" | xargs ls -t 2>/dev/null | head -5)

[ -z "$RECENT" ] && exit 0

# Build context injection
CONTEXT="## Recent Memories\n"
for f in $RECENT; do
    NAME=$(basename "$f" .md)
    # Extract description from frontmatter
    DESC=$(grep -m1 "^description:" "$f" 2>/dev/null | sed 's/^description: *//')
    TYPE=$(grep -m1 "^type:" "$f" 2>/dev/null | sed 's/^type: *//')
    if [ -n "$DESC" ]; then
        CONTEXT="${CONTEXT}- **${NAME}** (${TYPE}): ${DESC}\n"
    fi
done

echo -e "$CONTEXT"
