# App skills (`minitest app-skill`)

An **app skill** is a named procedure Mini loads during a test run to put the
app into a state it cannot reach through its own UI: calling the customer's test
backend, using an admin console, flipping a debug menu or a feature-flag cookie,
paying with a sandbox card. Mini sees every skill of the app by name and
description and loads one when the scenario needs it; scenarios can also
**link** skills so Mini loads them before starting.

Skills are only available when the workspace has them enabled. Otherwise every
command exits 4 with `Skills are not enabled for this workspace.`

## Skill or app knowledge?

App knowledge describes **the product**: screens, vocabulary, navigation,
expected behaviour. A skill describes **how to arrange test state**. Write a
skill when the knowledge:

- acts on something **outside the UI under test** (an API, an admin console, a
  cookie, a deep link that only test builds accept, a device setting), or is
  out-of-band knowledge only the customer's QA team has (a magic sandbox value,
  a debug-menu path, a static OTP mechanism);
- is **reused** by several scenarios, or has gotchas that are not obvious
  (idempotency, ordering, error codes, "markets never auto-close here");
- **arranges** state. A skill never judges a criterion: Mini still verifies the
  outcome in the app UI.

Keep in app knowledge anything that is about what the product does. Move out of
app knowledge any recipe, endpoint list, credential procedure or debug-menu
walkthrough you find there.

## Granularity

One skill per **system or capability** (`clutch-test-backend`,
`groundswell-admin-console`, `memrise-debug-menu`), not one per scenario and not
one per endpoint. Split a skill when its description can no longer say "Use
when …" in one sentence. Restrict it with `--platform` only when the procedure
truly differs per platform (a deep link that only exists on iOS).

## Writing a skill

- **Name:** kebab-case, at most 64 characters, prefixed with the app or system
  (`clutch-test-backend`). Names of Mini's built-in skills are rejected.
- **Description:** one sentence starting with "Use when …" or "Use to …". It is
  all Mini sees until it loads the skill, so name the states it can arrange.
- **Instructions:** markdown Mini follows step by step: base URL, auth, each
  call with its payload and what to capture from the response, how to hand the
  result to the app (deep link, cookie, login), known errors, cleanup.
- **Secrets:** never write a key, password or token in the instructions.
  Reference it as `$NAME` and set it with `app-skill secret set`; Mini receives
  it as an environment variable and the value is never shown again. The CLI
  warns when instructions use a `$NAME` that has no secret.

```bash
minitest --json --app <app_id> app-skill create clutch-test-backend \
  --description "Use to create personas, fund balances and create, close, resolve or void markets." \
  --instructions-file ./clutch-test-backend.md
printf '%s' "$KEY" | minitest --app <app_id> app-skill secret set clutch-test-backend CLUTCH_TEST_API_KEY
minitest --json --app <app_id> scenario-binding set-app-skills <story_id> --skill clutch-test-backend
```

## Maintaining a skill

Every change creates a new version and an audit entry (who, which channel,
which Mini session). Members edit directly with `update`. **Maintenance agents
do not edit**: when a setup step fails because the procedure drifted (a 422
naming a new required field, a renamed endpoint), propose the fix with the
evidence and let a member accept it.

```bash
minitest --json --app <app_id> app-skill propose clutch-test-backend \
  --reason "Run #482: POST /api/v1/test/markets returned 422 'category: field required'" \
  --instructions-file ./clutch-test-backend.md
```

A new proposal replaces the open one. A proposal written against an older
version can no longer be accepted.

## Commands

| Task | Command |
| --- | --- |
| List skills | `minitest --json --app ID app-skill list` |
| Read one | `minitest --json --app ID app-skill get <name>` |
| Create | `minitest --json --app ID app-skill create <name> --description "…" --instructions-file f.md [--platform ios]` |
| Edit | `minitest --json --app ID app-skill update <name> [--name new] [--description …] [--instructions-file f.md] [--platform …\|--all-platforms]` |
| Propose an edit | `minitest --json --app ID app-skill propose <name> --reason "…" --instructions-file f.md` |
| History (versions and audit events) | `minitest --json --app ID app-skill history <name-or-id>` |
| Restore a version | `minitest --json --app ID app-skill restore <name> --version 2` |
| Delete | `minitest --json --app ID app-skill delete <name>` |
| Delete and unlink scenarios | `minitest --json --app ID app-skill delete <name> --unlink-scenarios --yes` |
| Set a secret (stdin) | `printf '%s' "$V" \| minitest --app ID app-skill secret set <name> <SECRET_NAME>` |
| List / remove secrets | `minitest --json --app ID app-skill secret list <name>` / `secret unset <name> <SECRET_NAME>` |
| Link skills to a scenario | `minitest --json --app ID scenario-binding set-app-skills <story_id> --skill <name> [--skill …]` |
| Unlink all | `minitest --json --app ID scenario-binding set-app-skills <story_id> --clear` |

`delete` on a skill linked to scenarios exits 6 and lists them; nothing is
deleted until you pass `--unlink-scenarios --yes`. A deleted skill's history
stays readable by id.
