# Drafts with Mini (`minitest draft`)

A **draft** is what the webapp shows under *Drafts*: a branch of the app's test
suite plus a conversation with Mini about it. You say what should change, Mini
writes the scenarios, the draft checks them on a real build, and you merge the
proven change into the live suite. Everything you do here shows up in the webapp
at once, and a teammate can pick the same draft up there.

**Mini is the only author of a draft's branch.** Do not `df apply` into the
branch of a draft (its `draftFeatureId`): tell Mini what to change with
`draft message` instead. Use `minitest df` only for branches you write yourself
end to end, without Mini (see [`draft-features.md`](draft-features.md)).

## Setup

`minitest draft` talks to Conductor (`MINITEST_CONDUCTOR_URL`, production by
default; dev is `https://conductor.dev.minitap.ai`). It authenticates like every
other command: `minitest auth login`, or a customer `MINITEST_API_KEY` (`mtk_…`).
A key scoped to one app only reaches that app's drafts (other apps: exit 1 or 4).
Every command needs the app (`--app ID` or `MINITEST_APP_ID`).

## The loop

```bash
# 1. Open a draft with what you want; Mini starts at once.
#    --auto-check is optional: check each change once Mini wrote it.
DRAFT=$(minitest --json --app $APP draft create \
  --message "Cover refunds from the order page" --auto-check | jq -r .id)

# 2. Wait for Mini's reply (polls; progress on stderr, the draft on stdout).
minitest --json --app $APP draft get $DRAFT --watch
minitest --json --app $APP draft messages $DRAFT --last 1   # what Mini said

# 3. Answer what Mini asks, or keep talking.
minitest --json --app $APP draft ask list $DRAFT
minitest --json --app $APP draft message $DRAFT --message "Also on iOS"

# 4. Prove and merge.
minitest --json --app $APP draft check $DRAFT                   # unless --auto-check
minitest --json --app $APP draft get $DRAFT --watch --until settled
minitest --json --app $APP draft merge $DRAFT                   # only when state is ready
```

Long messages: `--message-file brief.md`, or `--message-file -` for stdin.

## Commands

| Goal | Command |
| ---- | ------- |
| List open drafts (or merged/discarded) | `draft list [--history]` |
| Read one: state, scenarios, open asks | `draft get ID` |
| Wait until it is stable | `draft get ID --watch [--until idle\|settled] [--timeout 900] [--interval 5]` |
| Open a draft | `draft create --message TEXT \| --message-file PATH [--title T] [--auto-check] [--auto-merge] [--idempotency-key K]` |
| Talk to Mini | `draft message ID --message TEXT \| --message-file PATH [--client-message-id K]` |
| Read the conversation | `draft messages ID [--last N]` |
| Interrupt Mini's current turn | `draft stop ID` |
| Rename / unattended settings | `draft update ID [--title T] [--auto-check\|--no-auto-check] [--auto-merge\|--no-auto-merge]` |
| Open asks | `draft ask list ID` |
| Answer an ask | `draft ask answer ID ASK_ID [--answer TEXT \| --answer-file PATH] [--field K=V]... [--field-file K=PATH]...` |
| Decline an ask | `draft ask decline ID ASK_ID [--reason R]` |
| Prove the draft on an open PR's head | `draft link-pr ID PR_NUMBER [--repo owner/name]` / `draft unlink-pr ID` |
| Check the changed scenarios | `draft check ID [--story SCENARIO_ID]... [--again] [--include-waiting]` |
| Build the commit a waiting draft needs | `draft build ID [--ref merge_commit\|main]` |
| Merge / throw away | `draft merge ID` / `draft discard ID` |
| Undo a merged draft | `draft revert ID [--reason R]` |
| "That failure is not an app bug" | `draft not-a-bug ID SCENARIO_ID [--reason R]` |

No command prompts and none takes `--yes`/`--force`: each is one explicit step
the server guards (merge refuses a draft that is not ready, etc.).

## Reading a draft

`draft get` returns the draft as JSON. The fields that drive your next step:

| Field | Meaning |
| ----- | ------- |
| `state` | `drafting` (Mini writing / nothing to check yet), `validating` (a check is running), `needs_you` (a person must decide), `ready` (proven: merge it), `blocked` (conflicts or a failing check), `waiting` (needs a newer build: `draft build` or ship one), `merged`, `discarded` |
| `stateReason`, `stateReasonCode` | Why, in words and as a code (`authoring`, `queued`, `not_checked`, `waiting_build`, `app_bug`, `rebase_conflict`, …) |
| `miniWriting` | Mini is answering right now |
| `needsUser` | Something waits on you: an open ask or a decision |
| `asks` | Mini's open questions, each with `id`, `question`, `askType`, `answerFields` |
| `stories` | The scenarios the draft adds, edits or removes, with their check state |
| `autoCheck`, `autoMerge` | The unattended settings |
| `linkedPr` | The PR the draft is proven on (`number`, `repo`), or absent |
| `waitingFor` | When `waiting`: the change it waits for, the PR, and the build in flight (`build.status`, `build.commitSha`, `build.etaSeconds`) |

`--watch` stops when:

- `--until idle` (default): Mini is not writing and has nothing queued — read its reply, answer, or send the next message;
- `--until settled`: idle, no check running **and** no build Conductor started for the draft in flight (e.g. a linked PR's head) — the verdict is in;
- either way, as soon as the draft is closed or `needsUser` is true.

It exits 1 after `--timeout` seconds and still prints the last snapshot; run it
again to keep waiting. Messages are answered one at a time, in the order sent.

## Answering asks

Each ask lists the fields its answer takes (`answerFields`: `key`, `label`,
`required`, `secret`). Free-text asks take `--answer`; structured ones take one
value per field:

```bash
minitest --json --app $APP draft ask answer $DRAFT $ASK \
  --field email=qa@shop.test \
  --field-file password=-  <<< "$QA_PASSWORD"      # secret: stdin or a file only
```

- A **secret** field is refused with `--field` (command lines end up in shell
  history and process lists): pass it with `--field-file KEY=PATH`, `-` for
  stdin. Only one field can read stdin.
- Secret values are never printed by the CLI nor echoed into Mini's
  conversation.
- Answering turns `autoMerge` off: a person is now in the loop. Turn it back on
  with `draft update` if you still want an unattended merge.
- `ask decline` tells Mini to carry on without it.

## Proving a draft on an open PR

When the scenarios test app code that is still in a pull request, link the draft
to the PR so it is proven on the PR's head commit, before the PR merges:

```bash
minitest --json --app $APP draft link-pr $DRAFT 128          # PR in the app's repository
minitest --json --app $APP draft check $DRAFT                 # builds the PR head if needed
minitest --json --app $APP draft get $DRAFT --watch --until settled --timeout 3600
```

- The check runs on a build of the PR's head. If none exists, Conductor builds
  that commit itself on every platform the app ships (no `draft build`, no
  upload) — the draft shows `state: waiting` with `waitingFor.build` until it
  lands, then checks it.
- New commits pushed to the PR: run `draft check $DRAFT --again` to prove the
  new head (`--again` re-runs proven scenarios too).
- Once the PR merges, the draft follows the merge commit; merge the draft after
  the PR.
- Never pass `--include-waiting` to a linked draft: it checks the newest build
  there is, which may not contain the PR.
- Only drafts you opened can be linked, on an app connected to GitHub (exit 6
  otherwise); an unknown PR exits 4. `draft unlink-pr` goes back to the latest
  build.

## Unattended drafts

`--auto-check` checks each change once Mini wrote it. `--auto-merge` merges the
draft on its own once every changed scenario is proven — never when it removes
scenarios, conflicts with the live suite, has a failing or blocking check, or
Mini judged a failure an app bug. Auto-merge without auto-check only merges
what you checked yourself.

## Retrying safely

`draft create` and `draft message` are idempotent. The CLI generates an id per
call and retries transport errors and 5xx with it; to retry a whole command
(e.g. after a crash), pass your own: `--idempotency-key` (create; the same key
returns the same draft) and `--client-message-id` (message; the same id never
posts twice — the JSON says `"created": false`).

## Errors

| Exit | Meaning | Do |
| ---- | ------- | -- |
| 1 | Bad input, or the key/user may not reach this app or tenant | Fix the flags or the credentials |
| 3 | Network or server error | Retry (with the same idempotency id) |
| 4 | Draft, scenario or ask not found (or outside the key's app) | Re-list |
| 6 | Not allowed in the draft's current state (closed, not ready, key reused for another app) | `draft get ID`, then decide |
