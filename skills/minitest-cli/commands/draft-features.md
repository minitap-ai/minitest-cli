# Draft features (`minitest df`)

A draft feature is a **branch of the app's test suite**: the tests a product
change will need, written before that change ships. It holds a *delta* against
main — new stories, edited ones, deletions, dependency changes — never a copy of
main. Everything you do to a branch goes through one atomic call, so a branch is
never half-written.

> To have Mini write the change for you, use `minitest draft` instead (see
> [`drafts.md`](drafts.md)). Never `df apply` into the branch of a Mini draft —
> Mini is its only author.

```bash
minitest --json --app $APP df list --status open
minitest --json --app $APP df create --title "Guest checkout" \
  --description "Behind the CHECKOUT_GUEST flag; needs a fresh cart per run."
minitest --json --app $APP df show $DF --view diff        # what it changes
minitest --json --app $APP df show $DF --view effective   # the suite it would run
minitest --json --app $APP df show $DF --view conflicts   # what a rebase could not settle
minitest --json --app $APP df apply $DF --changeset ./changeset.json
minitest --json --app $APP df delete $DF --force          # abandon, keeps history
```

`show --view diff` is the branch as a list of operations, in the same vocabulary
`apply` accepts — read a branch, reason about it, write the correction back
without translating. `--view effective` is the resolved suite: main with the
branch folded in, which is what a run against this branch would execute.
`--view conflicts` is the branch's mergetool, and is only interesting once
`rebaseState` is `conflicts`.

## Writing to a branch

`apply` takes a JSON file containing the whole request body:

```json
{
  "expectedMainRev": 7,
  "idempotencyKey": "add-guest-checkout-1",
  "ops": [
    { "op": "story.create", "tmpId": "guest", "fields": { "name": "Guest checkout", "type": "checkout" }, "criteria": ["Order completes without an account"] },
    { "op": "criterion.edit", "criterionId": "…", "expectedVersion": "…", "content": "…" },
    { "op": "dep.add", "childRef": "guest", "parentRef": "…" }
  ]
}
```

The eight operations are `story.create` / `story.edit` / `story.delete`,
`criterion.create` / `criterion.edit` / `criterion.delete`, and `dep.add` /
`dep.remove`. Four things to know:

- **Name main, not the branch.** Ops refer to the ids you see on the main suite.
  The server copies a story into the branch the first time you touch it; you
  never handle the copy's id. `tmpId` binds ops to each other inside one batch
  (a `dep.add` pointing at a story the same batch creates), and it is also how
  `show --view diff` names every story the branch invented — which is what makes
  that output replayable onto another branch as-is.
- **Unknown keys are rejected.** A misspelt field is a 422, not a silent drop, so
  a changeset you hand-edited fails loudly instead of half-applying.
- **Send the tokens you read.** `expectedMainRev` comes from `df show --view
  diff`; if main moved since that read, the apply is refused with 409 instead of
  landing on a suite you did not look at. Per-entity `expectedVersion` works the
  same way. Both are optional, and omitting them means writing blind.
- **Retries are free.** Reusing an `idempotencyKey` returns the first response
  rather than applying twice.

Semantics worth stating: `story.edit` fields you omit are left alone, whereas an
explicit `null` clears them. A batch is all-or-nothing, and a batch whose
dependency edges would close a cycle is rejected whole.

## Branch state

Two independent axes. `status` is `open` → `merging` → `merged`, or `abandoned`.
`rebaseState` is `in_sync` / `pending` / `rebasing` / `conflicts` and says
whether the branch has caught up with main. A branch is runnable only when it is
`open` **and** `in_sync`. `apply` is refused while `rebasing` (the branch is
being recomputed) and accepted while `conflicts` — resolving a conflict *is* an
apply. `df delete` abandons a branch without erasing it: the rows stay for audit
and drop out of `df list` unless you ask for them with `--status abandoned`.

## Resolving a conflict

When main and the branch changed the same thing, the rebase stops rather than
guess, and the branch sits at `rebaseState: conflicts`. `df show <id> --view
conflicts` is what tells you why:

```json
{
  "rebaseState": "conflicts",
  "mainRev": 4,
  "conflicts": [
    {
      "kind": "story_field_edit_edit",
      "reason": "both sides changed the same story fields",
      "storyId": "3ff0cb0e-…",
      "fields": ["test_profile_ids", "name"],
      "base":   { "name": "as pinned", "test_profile_ids": [] },
      "main":   { "name": "as pinned", "test_profile_ids": ["890408de-…"] },
      "branch": { "name": "renamed on the branch", "test_profile_ids": [] }
    }
  ]
}
```

`fields` names the keys the two sides disagree on, and `base` / `main` /
`branch` are the three versions of the node — the merge base, main as it stands
now, and the branch. You never have to go and read them yourself.

**The recipe.** Pick a side, copy its value for every key in `fields` into a
`story.edit` (or `criterion.edit`) op, and send `mainRev` back as
`expectedMainRev`:

```json
{
  "expectedMainRev": 4,
  "ops": [
    {
      "op": "story.edit",
      "storyId": "3ff0cb0e-…",
      "fields": { "test_profile_ids": ["890408de-…"], "name": "as pinned" }
    }
  ]
}
```

The inner keys of the three sides are already in the apply vocabulary, so the
copy is mechanical — that holds for every key `fields` can name, including
`test_profile_ids` and `test_file_ids`.

Three things to know:

- **A null side is not a null value.** `main: null` means main *deleted* the
  node; the human view prints `(no version)` for it. Resolving that is a
  `story.delete`, or an edit that re-states the branch's intent — not a copy.
- **`mainRev` is the token to send back.** It is printed on stdout (never inside
  a table title, which would wrap it). If main moved since your read, the apply
  is refused with 409 — exit code 6 — and you re-read and rebuild.
- **A successful apply hands the branch back to the sweep.** Applying against a
  branch in `conflicts` puts it back to `pending`; the server does not
  re-evaluate inside your write. Poll `df show --view conflicts` (or `df list`)
  until `rebaseState` settles to `in_sync`, or reports the next conflict.

## Exit code 6

`df` is the only group that returns 6, and **6 is not a transport failure**:
something you based the call on moved (a stale `expectedMainRev`, an
`expectedVersion` that no longer matches, a branch mid-rebase). Re-read the
resource, rebuild the request against what it now returns, and try **once** more
— retrying the same body loops forever.
