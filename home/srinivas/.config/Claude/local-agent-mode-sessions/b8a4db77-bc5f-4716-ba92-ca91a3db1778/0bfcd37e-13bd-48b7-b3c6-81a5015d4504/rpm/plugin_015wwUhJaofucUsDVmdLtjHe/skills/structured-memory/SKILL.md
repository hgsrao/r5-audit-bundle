---
name: structured-memory
description: "This skill should be used when the user asks to \"set up memory\", \"configure memory\", \"add memory to my project\", \"remember things across sessions\", or mentions wanting Claude to recall past decisions, preferences, or context between conversations. Also activates when the user asks about memory types, what to remember, or how the memory system works.\n"
version: '1.0.0'
---

# Structured Memory

Add persistent, categorized memory to any Claude Code project. Memories survive
across sessions and are organized by type — not dumped into a single file.

## Overview

The structured memory system has three components:

1. **Memory files** — individual markdown files with typed frontmatter, stored in
   the project's memory directory
2. **MEMORY.md index** — a concise pointer file loaded at session start (first 200
   lines are auto-loaded by Claude Code)
3. **A behavior rule** — teaches Claude when and how to save and recall memories

## Setup

### Step 1: Create the memory directory

Claude Code stores project memory at:
```
~/.claude/projects/<project-path>/memory/
```

This directory may already exist if auto-memory is enabled. The structured memory
system works alongside native auto-memory — it adds organization, not conflict.

### Step 2: Create MEMORY.md

Create or update `MEMORY.md` in the memory directory. This is the index — it contains
only links to memory files with brief descriptions. Keep it under 200 lines (Claude
Code truncates after that).

Use the template at `templates/MEMORY.md` as a starting point.

### Step 3: Add the behavior rule

Copy `templates/memory-rule.md` to `.claude/rules/memory.md` in the project. This
rule teaches Claude the decision trees for when to save and when to recall.

### Step 4: (Optional) Add the startup hook

The plugin includes a `SessionStart` hook that injects the 5 most recent memories
as context. This is optional — Claude Code already loads `MEMORY.md` at startup,
but the hook adds recency-weighted injection beyond what the index provides.

## Memory Types

Four types of memory, each serving a different purpose:

| Type | Purpose | When to Save |
|------|---------|-------------|
| **user** | Who the operator is — role, preferences, expertise | When you learn details about the user's background |
| **feedback** | How to work — corrections AND confirmations | When the user corrects or validates an approach |
| **project** | What's happening — goals, deadlines, decisions | When you learn about ongoing work or timelines |
| **reference** | Where to look — pointers to external systems | When you discover useful external resources |

See `references/memory-types.md` for detailed definitions with examples.

## Memory File Format

Each memory is a separate markdown file with YAML frontmatter:

```markdown
---
name: descriptive-name
description: one-line summary used for relevance matching
type: user | feedback | project | reference
---

Memory content here. For feedback and project types, structure as:

The rule or fact.

**Why:** The reason behind it.

**How to apply:** When and where this matters.
```

File naming: descriptive, kebab-case (e.g., `user-prefers-imperial.md`,
`feedback-no-trailing-summaries.md`).

## Decision Trees

### When to recall (before responding)

Recall when the message involves:
- Past decisions or preferences
- System knowledge or configuration
- Prior work or context from previous sessions
- References to "last time" or "we decided"

Skip when: direct follow-up already in context, no knowledge dependency.

### When to save (after responding)

**Step 1 — Does this exchange contain:**
- A user directive (preference, correction, "remember this")?
- A non-trivial reasoning conclusion?
- A durable observed fact?

If no to all, stop.

**Step 2 — Does an overlapping memory exist?**
- Yes, incremental info → update the existing memory
- Yes, contradicts → replace the existing memory
- No overlap → create new

**Step 3 — Is it worth storing?**
- Could a single query recover this? → No, skip
- Multi-source synthesis? → Yes, store
- User-specific context no search can recover? → Yes, store

### What NOT to save

- Code patterns or architecture derivable from reading the codebase
- Git history or recent changes (`git log` is authoritative)
- Debugging solutions (the fix is in the code)
- Ephemeral task details only useful in the current session
- Anything already documented in project files

## Working With Native Auto-Memory

Claude Code's built-in auto-memory writes to the same `MEMORY.md` file. The
structured memory system is compatible:

- Native auto-memory entries (without typed frontmatter) continue to work
- Structured memory files (with frontmatter) add categorization on top
- Both are loaded at session start
- Over time, migrate unstructured entries into typed memory files

The key difference: native auto-memory is a scratch pad. Structured memory is
a knowledge system with intent behind every entry.
