# Bug triage policy (DRAFT for the owner's review)

Severity answers "how bad is it when it happens". Priority answers "when do we fix it". They are separate decisions.
Severity never gets lowered to unblock a pull request.

## Severity (labels `sev:*`)

| Severity | Definition | Examples in this project |
|---|---|---|
| `sev:critical` | The system is unusable, data is lost or corrupted, or a security boundary is broken | Server error (500) on a core flow; a loan lost or duplicated; the database loses data after a restart; an authorization bypass; secrets exposed |
| `sev:major` | A key function is broken and there is no reasonable workaround | Cannot issue or return a book; the book list does not load; a wrong fine is charged; the UI crashes on a main screen |
| `sev:minor` | The function works with flaws, or a workaround exists | Wrong message text; a validation error shown on the wrong field; a number formatted wrongly; a rare edge case |
| `sev:trivial` | Cosmetic or no effect on use | Typo, spacing, a misaligned element, a log wording |

Rule of thumb: ask three questions: **Does it lose or expose data or break security?** (critical). **Can the user still
reach the goal?** (no: major). **Is there a workaround or limited impact?** (yes: minor or trivial).

## Priority (labels `P1`-`P3`)

| Priority | Meaning | Default for |
|---|---|---|
| `P1` | Fix now, before anything else; blocks the pull request or the release | `critical`, and `major` found in the feature under test |
| `P2` | Fix in the current or next planned work | `major` outside the feature under test; `minor` found in the feature under test |
| `P3` | Fix when there is time; may stay in the backlog | `minor` outside the feature; `trivial` |

Priority can be raised above the default by the owner for business reasons (visible to many users, a demo, a deadline),
and lowered only by the owner and with a written reason.

## Blocking decision (pull request under test)

| Found in the feature under test | Blocks the PR? | What happens |
|---|---|---|
| `critical` | yes | P1, back to the developer, QA re-verifies |
| `major` | yes | P1, back to the developer, QA re-verifies |
| `minor` | no, unless it breaks an acceptance criterion | P2, backlog; listed in the "ready to merge" message |
| `trivial` | no | P3, backlog |
| any, found **outside** the feature (existing behaviour) | no | its own severity and priority; a separate ticket |

A bug that violates an **acceptance criterion** always blocks, whatever its severity: the feature is not done.

## Hard rules

- Security issues and data loss are always `critical` and `P1`.
- A bug found by a test in the project's own suite on `main` (a regression) is at least `major`.
- "Won't fix" and "works as designed" decisions belong to the owner; record the reason in the ticket.
- Every fixed bug gets a **regression test** before it is closed. QA closes the bug after verifying the fix.
- Duplicates are linked to the original; the owner approves closing.

## What a bug report must contain

A bug without these is returned to the reporter. Title format: `[bug][AREA] short symptom`.

```markdown
**Summary:** one sentence.
**Environment:** where it happens (cluster / local, branch or commit, browser, language ru/en).
**Steps to reproduce:**
1. ...
2. ...
**Expected:** what should happen (cite the acceptance criterion or requirement ID).
**Actual:** what happens (error text, status code, screenshot, log excerpt; no secrets).
**Frequency:** always / sometimes (how often) / once.
**Evidence:** failing test name and path, trace or link, request id from the logs when available.
**Severity / Priority:** proposed `sev:*` and `P*` with a one-line reason.
**Related:** ticket, PR, requirement ID.
```

Labels on creation: `bug`, `sev:*`, `P*`, `area:*`, and `needs-triage` if severity or priority is not yet confirmed.

## Lifecycle of a bug

`Backlog` (triaged) -> `In progress` (developer fixing) -> `QA` (verification with the regression test) -> `Done`.
Blocking bugs are linked to the ticket under test and send it back to `In progress`.

## Open points for the owner to decide

1. Are the default priorities above right for this project? (for example, should `minor` in the feature under test ever block?)
2. Target fix times, if you want them (for example P1 within the same working session, P2 within a week).
3. Should a `major` bug outside the feature under test block a release, or only the pull request?
