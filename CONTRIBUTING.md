# Contributing

This repository follows the [Friday Labs Engineering Standard](../docs/engineering-standard.md).
This file is the short version — the part you need to open your first pull
request. Where the two disagree, the Standard wins and this file is the bug.

## Fresh clone to running tests

This is a **Frappe app** (`randompack_ai/hooks.py` + `randompack_ai/modules.txt`). It does not run
on its own; it runs inside a bench.

> **This repository does not declare which Frappe major it targets.**
> Add the block below to `pyproject.toml` and the commands in this section, the
> `Tests (bench)` CI job and a contributor's local bench all start agreeing —
> they read the same declaration. Until then CI runs lint only, and that is
> recorded as an exemption in the Engineering Standard §10.
>
> ```toml
> [tool.bench.frappe-dependencies]
> frappe = ">=16.0.0,<17.0.0"
> ```

```bash
# What CI runs today, and what you can run without a bench:
pipx run ruff==0.15.8 check .
pipx run ruff==0.15.8 format --check .

# Once the declaration above exists, this is the full loop:
pip install frappe-bench
bench init --frappe-branch version-16 frappe-bench && cd frappe-bench
bench get-app /path/to/this/clone
bench --site dev.localhost install-app randompack_ai
bench --site dev.localhost run-tests --app randompack_ai
```

Budget: **under 1 minute** for the lint loop. The bench loop is under 30 minutes
cold, under 3 minutes warm.

## Before you push

Install the hooks once. They run the same lint and format that CI runs, so a
red CI run on formatting should be impossible.

```bash
pip install pre-commit
pre-commit install
```

## The loop

1. **Branch** off the default branch: `feat/`, `fix/`, `docs/`, `chore/`,
   `refactor/`, `test/`, `ci/` or `perf/` + a short slug.
   `feat/brand-brief-intake`, not `mira-wip`.
2. **Commit** with `<type>(<scope>): <summary>` in the imperative mood.
   `fix(intake): reject a brief with no client` — not `fixed stuff`.
   CI checks every subject on the branch.
3. **Open a PR** and fill in every section of the template. An empty
   "How it was verified" is a request for changes.
4. **Keep it small.** Under ~400 changed lines excluding lockfiles and
   generated files. A larger PR is allowed but must say in its description why
   it could not be split.
5. **Get one approval** from a code owner and a green `required` check. Both
   are enforced by branch protection; neither can be self-granted.
6. **Squash merge.** One PR becomes one commit on the default branch, and its
   subject is the release note.

## What blocks a merge

- `required` is not green.
- No approving review from a code owner.
- An unresolved review thread.
- A commit subject that is not a conventional commit.
- A credential-shaped file in the diff.

## What never goes in a commit

Secrets, tokens, API keys, certificates, `.env` files, customer data, database
dumps. Config goes in `.env.example` with a placeholder and a comment; the real
value goes in the platform secret store. If you have already pushed a secret,
stop and escalate — rotating it comes first, rewriting history second.
