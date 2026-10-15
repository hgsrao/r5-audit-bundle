# claude-memory

> **Archived 2026-09-23.** Claude Code now ships this four-type, frontmatter-file memory convention natively in its auto-memory prompt, so the plugin's core is redundant with stock. The author's current memory design (a content-bearing working file over a graph store with a single mechanical write path) is documented in the [persistent-agent-guide memory chapter](https://github.com/tars23364-bit/persistent-agent-guide/blob/main/docs/02-memory.md). The when-to-save decision tree in `skills/structured-memory/references/decision-tree.md` is still a fine read.

A Claude Code plugin that adds structured, categorized memory to your projects.

## What it does

Claude Code has built-in auto-memory that writes notes to `MEMORY.md`. This plugin builds on that foundation with:

- **Typed memories** — four categories (user, feedback, project, reference) with distinct purposes
- **Frontmatter format** — each memory file has structured metadata for relevance matching
- **Decision trees** — clear rules for when to recall and when to save
- **Startup injection** — a hook that surfaces recent memories at session start
- **Templates** — ready-to-use starter files for MEMORY.md and behavior rules

The plugin teaches Claude *how* to manage memory with intent — not just what to write, but when to write, when to update, and when to skip.

## Install

```bash
claude plugins install claude-memory
```

Or test locally:

```bash
claude --plugin-dir /path/to/claude-memory
```

## Quick Start

After installing, ask Claude:

> "Set up structured memory for this project"

Claude will:
1. Create the memory directory structure
2. Set up MEMORY.md as an index
3. Add a memory rule to `.claude/rules/`
4. Start categorizing memories going forward

## Memory Types

| Type | Purpose | Example |
|------|---------|---------|
| **user** | Who you are — role, expertise, preferences | "Senior backend engineer, new to React" |
| **feedback** | How to work — corrections and confirmed approaches | "Don't mock the database in integration tests" |
| **project** | What's happening — goals, deadlines, decisions | "Merge freeze starts March 5 for release cut" |
| **reference** | Where to look — pointers to external systems | "Pipeline bugs tracked in Linear project INGEST" |

## File Format

Each memory is a standalone markdown file:

```markdown
---
name: feedback-no-mocking
description: Integration tests must use real database, never mocks
type: feedback
---

Integration tests must hit a real database, not mocks.

**Why:** Mock/prod divergence masked a broken migration last quarter.

**How to apply:** All files in tests/integration/ use real DB connections.
```

## What's Included

```
claude-memory/
├── skills/structured-memory/
│   ├── SKILL.md              # Core skill — memory methodology
│   ├── references/
│   │   ├── memory-types.md   # Detailed type definitions
│   │   └── decision-tree.md  # When to save, recall, skip
│   ├── examples/             # Sample memory files for each type
│   └── templates/
│       ├── MEMORY.md         # Starter index file
│       └── memory-rule.md    # Behavior rule for .claude/rules/
└── hooks/
    ├── hooks.json            # SessionStart memory injection
    └── scripts/
        └── memory-context.sh # Injects recent memories at startup
```

## Compatibility

Works alongside Claude Code's native auto-memory. Structured memories add
categorization and intent on top of the existing system — they don't replace it.

## License

MIT
