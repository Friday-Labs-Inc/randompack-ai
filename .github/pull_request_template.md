<!--
Friday Labs PR template. Engineering Standard §3.
Every heading below is checked by the reviewer; an empty section is a request
for changes, not a detail. Delete nothing — write "n/a" and why.
-->

## What changed

<!-- One paragraph. What a reader of the changelog needs, not a diff summary. -->

## Why

<!-- The problem this solves. Link the issue: [FRI-123](/FRI/issues/FRI-123) -->

## How it was verified

<!--
The command you ran and what it printed, or the CI job that proves it.
"CI is green" alone is not verification when the change is not covered by a test
— say so explicitly instead (Standard §6).
-->

- [ ] Tests added or changed for the behaviour this PR alters
- [ ] Ran locally:  <!-- e.g. `bench --site dev run-tests --app studio_os` -->
- [ ] No behaviour change (docs / config / CI only)

## Risk and rollback

<!-- What breaks if this is wrong, and the exact way back. For a migration or a
     patch, name the patch and whether it is reversible. -->

## Checklist

- [ ] Commit subjects are `<type>(<scope>): <summary>` (Standard §3)
- [ ] No secret, credential, token or customer data in the diff (Standard §8)
- [ ] Config added to `.env.example` / documented, not hard-coded (Standard §8)
- [ ] Docs updated if this changes how someone runs or deploys the repo
- [ ] `required` CI check is green
