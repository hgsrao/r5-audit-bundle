# Memory Decision Trees — Detailed Reference

## Recall Decision Tree

Run this before responding to a new user message.

```
User sends a message
│
├─ Is this a direct follow-up within a topic already fully in context?
│  └─ Yes → SKIP recall
│
├─ Does it reference past sessions, decisions, or preferences?
│  └─ Yes → RECALL
│
├─ Does it depend on knowledge beyond the current conversation?
│  └─ Yes → RECALL
│
├─ Does it involve system knowledge, configuration, or prior work?
│  └─ Yes → RECALL
│
└─ None of the above → SKIP recall
```

**How to recall:** Read the MEMORY.md index. Scan memory file descriptions for
relevance. Load the specific memory files that match. Don't load everything —
the index exists so you can be selective.

---

## Save Decision Tree

Run this after every substantive response.

```
Exchange complete
│
├─ Step 1: Does this exchange contain any of these?
│  ├─ (a) User directive — preference, decision, correction, explicit "remember this"
│  ├─ (b) Reasoning conclusion — non-trivial judgment from multi-source synthesis
│  └─ (c) Durable observed state — system fact, environment detail, finding
│     └─ No to all → STOP (don't save)
│
├─ Step 2: Does a highly overlapping memory already exist?
│  ├─ Yes, incremental new info → UPDATE (merge into existing file)
│  ├─ Yes, contradicts/supersedes → REPLACE (update the file)
│  └─ No significant overlap → CREATE (new file)
│
└─ Step 3: Is it worth storing?
   ├─ Rebuilding from scratch costs more than storing + recalling?
   │  ├─ Single-query public facts → No, skip
   │  ├─ Multi-source synthesis with non-obvious conclusions → Yes, save
   │  └─ User-specific context no search engine can recover → Yes, save
   └─ No → STOP
```

---

## What NOT to Save

These categories should never be stored in memory, even if the user asks:

| Category | Why Not | What to Do Instead |
|----------|---------|-------------------|
| Code patterns & architecture | Derivable from reading the codebase | Read the code |
| Git history & recent changes | `git log` / `git blame` are authoritative | Use git tools |
| Debugging solutions | The fix is in the code; commit message has context | Read the diff |
| Project docs (if they exist) | Already documented in CLAUDE.md or similar | Read the docs |
| Ephemeral task details | Only useful in the current session | Use a task list |
| Secrets, API keys, tokens | Security risk | Use keychain/env vars |

**If the user asks to save something in an excluded category:** Ask what was
surprising or non-obvious about it — that's the part worth keeping. The raw
data isn't, but the insight might be.

---

## Memory Maintenance

### Updating memories

When new information arrives that relates to an existing memory:
- Read the existing memory file
- Merge the new information in
- Update the description in frontmatter if the scope changed
- Don't create a duplicate

### Removing memories

Remove a memory when:
- The user explicitly asks to forget something
- The information is demonstrably outdated
- A project memory's deadline has passed and the context is no longer relevant
- A reference memory points to a resource that no longer exists

### Keeping the index clean

MEMORY.md should stay under 200 lines. If it grows beyond that:
- Archive completed project memories
- Consolidate related memories into fewer files
- Remove entries for deleted memory files
- Keep descriptions concise — one line per entry
