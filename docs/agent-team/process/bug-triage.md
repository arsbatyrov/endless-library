# Bug triage policy (DRAFT for the owner's review)

Bugs have **one** rating: **Priority**, with four levels: **Critical, High, Mid, Low**. There is no separate severity.
The **tester sets the priority**; the owner can override it. Priority is never lowered to unblock a pull request.

The bug issue template is `.github/ISSUE_TEMPLATE/bug.yml` (the form has a required Priority field).

## Priority levels (labels `priority:*`)

| Priority | Label | Definition | Examples in this project | Fix |
|---|---|---|---|---|
| **Critical** | `priority:critical` | The system is unusable, data is lost or corrupted, or a security boundary is broken | A core flow returns 500; a loan is lost or duplicated; data disappears after a restart; an authorization bypass; secrets exposed | Immediately, before anything else |
| **High** | `priority:high` | A key function is broken and there is no reasonable workaround | Cannot issue or return a book; the book list does not load; a wrong fine is charged; the UI crashes on a main screen | In the current work |
| **Mid** | `priority:mid` | The function works with flaws, or a workaround exists | Wrong message text; a validation error on the wrong field; a number formatted wrongly; a rare edge case | Planned (current or next work) |
| **Low** | `priority:low` | Cosmetic or minimal impact | Typo, spacing, a misaligned element, a log wording | When there is time; may stay in the backlog |

How to choose, in three questions:
1. Does it lose or expose data, or break security? **Critical**.
2. Can the user still reach the goal? If not, **High**.
3. Is there a workaround or a limited impact? **Mid** (flaws that matter) or **Low** (cosmetic).

The owner may raise a priority for business reasons (visible to many users, a demo, a deadline) and may lower it with a
written reason in the ticket.

> Feature tickets still carry `P1`-`P3` labels and the board field Priority (P1-P3). Bugs use the four `priority:*` labels
> defined here. Whether to unify both on one scale is an open decision (see the end of this file).

## Does the bug block the pull request?

| Found in the feature under test | Blocks the PR? | What happens |
|---|---|---|
| Critical | yes | Back to the developer, QA re-verifies |
| High | yes | Back to the developer, QA re-verifies |
| Mid | no, unless it breaks an acceptance criterion | Backlog, listed in the "ready to merge" message |
| Low | no | Backlog |
| Any priority, found **outside** the feature (existing behaviour) | no | Its own ticket and priority |

A bug that violates an **acceptance criterion** always blocks, whatever its priority: the feature is not done.

## Hard rules

- Security issues and data loss are always **Critical**.
- A regression found by the project's own test suite on `main` is at least **High**.
- "Won't fix" and "works as designed" decisions belong to the owner; record the reason in the ticket.
- Every fixed bug gets a **regression test** before it is closed (the closing checklist in the template requires it).
  QA closes the bug after verifying the fix on the deployed environment.
- Duplicates are linked to the original; the owner approves closing.

## What a bug report must contain

The form asks for all of this; a report without the required fields is returned to the reporter.
Title format: `[Bug][area] short symptom`.

| Field | Why it matters |
|---|---|
| Summary | One sentence: what is wrong and where |
| Priority and why | The tester's decision with a one-line reason |
| Area | api, web, android, infra, ci, docs |
| Requirement ID / related ticket | Traceability: which criterion is violated |
| How was the bug found | Manual, exploratory, automated (local or CI), deployed environment, review: used for quality metrics |
| Is it a regression, first seen in | Regression rate and the last good / first bad version |
| Environment | Cluster or local, commit, browser, language, OS |
| Steps to reproduce, expected, actual | The core of the report |
| Frequency | Always, sometimes, once |
| Evidence | Failing test, trace, request id, screenshot, logs (no secrets) |

Labels after creation: `bug`, `priority:*`, `area:*`; remove `needs-triage` once the priority is confirmed.

## Lifecycle of a bug

`Backlog` (triaged) -> `In progress` (developer fixing) -> `QA` (verification with the regression test) -> `Done`.
Blocking bugs are linked to the ticket under test and send it back to `In progress`.

## Metrics this policy enables

Bugs by priority, by "how found", regression rate, bugs escaped to the deployed environment (found there instead of earlier),
time from report to fix. These are the numbers a QA lead reports.

## Open points for the owner to decide

1. Are the default blocking rules right (Critical and High block; Mid and Low do not)?
2. Target fix times, if you want them (for example Critical within the same working session, High within the current work, Mid within a week).
3. Should the existing `sev:*` labels (not used any more) be deleted?
4. Should feature tickets move from `P1`-`P3` to the same four levels (Critical, High, Mid, Low), so there is one scale in the project?
