---
name: project-merge-freeze-march
description: Non-critical merge freeze from 2026-03-05 for mobile release branch cut
type: project
---

Merge freeze on non-critical PRs begins 2026-03-05. Mobile team is cutting a
release branch and needs a stable main.

**Why:** Coordinated release process — any merge conflict or broken test on main
delays the mobile release by at least a day.

**How to apply:** Prioritize critical bug fixes and release-blocking PRs. Defer
refactoring, nice-to-have features, and dependency updates until after the freeze
lifts. If unsure whether something is critical, ask before merging.
