# Agent workflow

How the roles work together. The owner is the product owner and the final decision maker. The orchestrator (the
process manager skills in the main session) moves tickets; the subagents do the role work. Roles talk to each other **only
through the ticket**: its description, structured comments, labels and the board **Status**.

## Statuses (project board "Endless Library", field Status)

| Status | Meaning | Who works | Exit condition |
|---|---|---|---|
| `Idea` | Raw idea, not yet analysed | owner | `/idea` starts the interview |
| `Analysis` | Analyst interview or draft in progress; questions open | analyst + owner | owner confirms criteria, ticket created |
| `Ready` | Criteria confirmed, DoR met | nobody (waiting) | `/next` starts the design |
| `Design` | Architect's design written, waits for the owner's confirmation | architect, owner | owner confirms design/ADR (gate) |
| `Test plan` | QA's test strategy written, waits for the owner's confirmation | QA, owner | owner confirms test plan (gate) |
| `In progress` | Developer implements; fixes review findings and bugs | developer | PR opened, own tests green |
| `In review` | Reviewer reviews the code | reviewer | verdict Approve (else back to `In progress`) |
| `QA` | QA writes and runs API/contract/e2e/smoke tests, explores | QA | pass (else bugs go back to `In progress`) |
| `Ready to merge` | PR green and approved; the owner decides | owner | owner says yes, orchestrator merges |
| `Done` | Merged and closed | | |
| `Blocked` | Waiting for a decision or an external action | owner | owner unblocks |

Labels describe the ticket (`feature`, `bug`, `task`, `test`, `P1`-`P3` for features, `priority:critical|high|mid|low` for bugs, `area:*`); **Status says where it is**.

## Owner gates (nothing proceeds without an explicit yes)

1. **Acceptance criteria**: the analyst's draft, before any ticket is created.
2. **Design and ADR**: before test planning and code.
3. **Test plan**: the pyramid split and who writes which tests.
4. **Merge**: after "ready to merge"; the orchestrator merges only after the owner's yes in the same session.

Always the owner's decision as well: creating or closing tickets outside this flow, repository or board settings, secrets,
deployments, new dependencies, anything outside the repository.

## Handoff comment format

Every role posts exactly one comment per stage on the ticket (English):

```markdown
## <Role>   (Analyst | Architect | QA | Developer | Reviewer)

**Stage:** <what this stage was>
**Result:** <ready | needs answers | blocked | approve | changes requested | pass | blocked by bugs>
**Summary:** <3-6 lines>
**Artifacts:** <links: PR, ADR path, test files, bug issues>
**Verified:** <commands run and their results; "not verified" if so>
**Open questions:** <numbered, each with a proposed default>
**Next:** <who acts next and what they need>
```

Owner decisions are recorded as short comments by the orchestrator (`Owner confirmed design`, `Owner confirmed test plan`,
`Owner approved merge`).

## Loops and limits

- Review loop: Reviewer "Changes requested" returns to the developer; at most **3** loops, then the owner decides.
- QA loop: blocking bugs return to the developer with the bug linked; QA re-verifies after the fix.
- Work in progress: **one ticket at a time** through `In progress`, `In review` and `QA`.
- Ambiguity: a role that finds unclear or contradictory criteria stops and reports; it never guesses.

## Ownership of tests

The **test plan** (gate 3) assigns every test to a writer. Default: unit and component-level tests by the **developer**;
API, contract, UI e2e and smoke tests by **QA**. The developer does not edit QA-owned tests; QA does not edit production code.
Every test links to a requirement ID; every fixed bug gets a regression test.

## Definition of Ready and Done

DoR and DoD are the checklists in `.github/ISSUE_TEMPLATE/feature.yml`. A ticket moves to `Ready` only with confirmed
Given/When/Then criteria; it is `Done` only when the DoD list is complete and the PR is merged.

## Branches, commits, PRs

Branch `feat/<REQ-ID>-<slug>` (or `fix/`, `docs/`, `chore/`) from an up-to-date `main`. PR description in English with
`Fixes #N`, how it was verified. Merge commit with branch deletion, after all required checks are green.

## Escalation

If a role is blocked, a check is red for an unclear reason, a test seems wrong, or a rule in `CLAUDE.md` conflicts with the
ticket, the orchestrator stops and asks the owner with the evidence.

## Lessons learned (fill in after the pilot)

- What worked:
- What was slow or costly:
- Prompt changes made:
- Rules to add (candidates: enforcement hook, GitHub Actions automation):
