# Memory Types — Detailed Reference

## User Memories

Contain information about the operator's role, goals, responsibilities, and
knowledge. The aim is to tailor future behavior to who the operator actually is.

**When to save:** When you learn details about the operator's role, preferences,
responsibilities, or expertise level.

**How to use:** When your work should be informed by the operator's profile. A
senior engineer gets different explanations than a first-time coder.

**Examples:**

> User: "I'm a data scientist investigating what logging we have in place"
> → Save: user is a data scientist, currently focused on observability/logging

> User: "I've been writing Go for ten years but this is my first time touching React"
> → Save: deep Go expertise, new to React — frame frontend explanations in
>   terms of backend analogues

**Structure:** Lead with the relevant fact, then context for how it should shape
interactions.

---

## Feedback Memories

Guidance the operator has given about how to approach work — both corrections
and confirmations. These are critical for staying coherent across sessions.

**When to save:** Any time the operator corrects your approach ("no not that",
"don't do X") OR confirms a non-obvious approach worked ("yes exactly", "perfect,
keep doing that"). Corrections are obvious; confirmations are quieter — watch
for them.

**How to use:** Let these memories guide behavior so the operator doesn't repeat
the same guidance twice.

**Examples:**

> User: "don't mock the database in these tests — we got burned last quarter"
> → Save: integration tests must hit a real database, not mocks.
>   **Why:** Prior incident where mock/prod divergence masked a broken migration.
>   **How to apply:** All test files in tests/integration/ use real DB connections.

> User: "yeah the single bundled PR was the right call here"
> → Save: for refactors in this area, operator prefers one bundled PR over many
>   small ones. Confirmed after this approach was chosen — a validated judgment
>   call, not a correction.

**Structure:** Lead with the rule, then **Why:** (the reason) and **How to apply:**
(when/where this kicks in). Knowing why lets you judge edge cases.

---

## Project Memories

Information about ongoing work, goals, initiatives, or decisions that isn't
derivable from code or git history.

**When to save:** When you learn who is doing what, why, or by when. Always
convert relative dates to absolute dates ("Thursday" → "2026-03-05") so the
memory remains interpretable later.

**How to use:** Understand the broader context behind requests and make better
informed suggestions.

**Examples:**

> User: "we're freezing all non-critical merges after Thursday"
> → Save: merge freeze begins 2026-03-05 for release cut. Flag any non-critical
>   PR work scheduled after that date.
>   **Why:** Mobile team is cutting a release branch.
>   **How to apply:** Prioritize critical PRs, defer nice-to-haves.

> User: "the auth rewrite is driven by legal compliance, not tech debt"
> → Save: auth middleware rewrite motivated by legal/compliance requirements
>   around session token storage.
>   **Why:** Legal flagged the current implementation.
>   **How to apply:** Scope decisions should favor compliance over ergonomics.

**Structure:** Lead with the fact or decision, then **Why:** and **How to apply:**.
Project memories decay fast — the why helps future sessions judge whether the
memory is still relevant.

---

## Reference Memories

Pointers to where information lives in external systems. These remember where
to look, not what's there.

**When to save:** When you learn about resources in external systems and their
purpose.

**How to use:** When the operator references an external system or asks about
information that might live outside the project.

**Examples:**

> User: "check the Linear project 'INGEST' for pipeline bug context"
> → Save: pipeline bugs are tracked in Linear project "INGEST"

> User: "the Grafana board at grafana.internal/d/api-latency is what oncall watches"
> → Save: grafana.internal/d/api-latency is the oncall latency dashboard —
>   check when editing request-path code

**Structure:** Lead with where the resource is, then what it's for and when
to reference it.
