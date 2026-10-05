# Bug triage policy (DRAFT for the owner's review)

Bugs have **one** rating: **Priority**, with four levels: **Critical, High, Mid, Low**. There is no separate severity.
The **tester sets the priority**; the owner can override it. Priority is never lowered to unblock a pull request.

The bug issue template is `.github/ISSUE_TEMPLATE/bug.yml` (the form has a required Priority field).

## Priority levels (labels `priority:*`)

| Priority | Label | Definition | Examples in this project | Fix |
|---|---|---|---|---|
| **Critical** | `priority:critical` | The system is unusable, data is lost or corrupted, or a security boundary is broken | A core flow returns 500; a loan is lost or duplicated; data disappears after a restart; an authorization bypass; secrets exposed | ASAP: drop other work |
| **High** | `priority:high` | A key function is broken and there is no reasonable workaround | Cannot issue or return a book; the book list does not load; a wrong fine is charged; the UI crashes on a main screen | Within 1 day |
| **Mid** | `priority:mid` | The function works with flaws, or a workaround exists | Wrong message text; a validation error on the wrong field; a number formatted wrongly; a rare edge case | Within 1 week |
| **Low** | `priority:low` | Cosmetic or minimal impact | Typo, spacing, a misaligned element, a log wording | Within 2 weeks |

**Target fix times** (from the moment the priority is confirmed): Critical **ASAP**, High **within 1 day**, Mid **within 1 week**,
Low **within 2 weeks**. A missed target is reported to the owner by the orchestrator; it is a signal to re-plan, not a reason
to lower the priority.

How to choose, in three questions:
1. Does it lose or expose data, or break security? **Critical**.
2. Can the user still reach the goal? If not, **High**.
3. Is there a workaround or a limited impact? **Mid** (flaws that matter) or **Low** (cosmetic).

The owner may raise a priority for business reasons (visible to many users, a demo, a deadline) and may lower it with a
written reason in the ticket.

> The same four levels and labels (`priority:*`) are used for **feature tickets** too (business urgency, set by the owner),
> and for the board field Priority. There is one scale in the project.

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

## Decisions made by the owner

1. Blocking rules: accepted as written (Critical and High block the PR; Mid and Low do not; an acceptance-criterion violation always blocks).
2. Target fix times: Critical ASAP, High within 1 day, Mid within 1 week, Low within 2 weeks.
3. The `sev:*` labels were deleted; there is no separate severity.
4. Feature tickets use the same four priority levels as bugs (`P1`-`P3` were migrated: P1 to High, P2 to Mid, P3 to Low).
