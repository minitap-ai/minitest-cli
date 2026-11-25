# Personas and test accounts (`minitest persona`, `minitest test-account`)

A **persona** is who Mini plays in a scenario ("Denmark buyer"). A **test account**
is one real login of a persona; a persona has one or more and Mini signs in with one
of them, spreading runs across them. **Credentials** are a test account's secrets.
Scenarios pick personas, never logins.

```bash
minitest --json --app $APP persona create --name "Denmark buyer" --about "Ships to DK" --exclusive
printf "%s" "$PW" | minitest --json --app $APP test-account add --persona "Denmark buyer" \
  --username "tester7@example.com" --password-stdin
printf "%s" "$PW" | minitest --json --app $APP test-account add --persona "Denmark buyer" \
  --username "tester15@example.com" --password-stdin
minitest --json --app $APP persona pool "Denmark buyer"
minitest --json --app $APP scenario-binding set-personas $SCENARIO --persona "Denmark buyer"
```

## Exclusive use

`persona exclusive <persona> on` keeps each test account to one run at a time: with two
accounts, up to two runs of the persona's scenarios go at once, and a third waits for a
free account. Add accounts to run more in parallel. Off (the default), runs never wait
and are spread over the accounts. It cannot be turned on for "New user".

## Pool

`persona pool` lists every account as `free`, `in_use` (with the run, its batch and its
platform holding it; Mini exploring the app, checking a scenario or using it on a device
shows as `exploration`, `validation` or `device_session`; a run of another workspace using
the same login shows as `other_workspace`, without ids) or `cooling_down` (until when, and why: `blocked`,
`rate_limited`, `logged_out`, `verification_failed`). An account of a persona without
exclusive use can have several holders (`holderCount`). `persona list` and `persona get`
carry the same counts (`freeCount`, `inUseCount`, `coolingDownCount`, `accountCount`).
`test-account clear-cooldown <id>` puts a cooled account back into rotation.

## Binding scenarios

`scenario-binding set-personas <scenario> --persona A --persona B` replaces the personas a
scenario plays (`--clear` unbinds them all; the scenario then runs as New user).
`list-personas` reads them. A persona needs at least one test account before a scenario
can play it (409 otherwise). `scenario create|update --persona` set them too
(`update --clear-personas` unbinds them all).

On a draft feature branch, pass `--draft-feature <df_id>` with the scenario's **main** ID.
In a changeset (`df apply`), `story.create` and `story.edit` ops take
`"personaIds": ["…"]`; `df show --view diff` reports them as `persona_ids`.

## Default persona

`persona default <persona>` sets the persona a scenario plays when `scenario create` gets no
`--persona`; `persona default --clear` removes it, and such scenarios play New user. The
backend stores the default on one test account (the persona's oldest), so `test-account list`
marks that account `★` in its Default column. The persona needs a test account first.

## Shared by Minitap

`test-account list --shared` lists the logins Minitap maintains for every app (Google
sign-in accounts, 2-Step Verification included), with their `personaId`. A scenario plays
one like any persona: `--persona <personaId>`. They are read-only: no `test-account` or
`persona` command changes them. `test-account list` (no flag) lists the app's own accounts
with their persona.

## Changing accounts

- `test-account update <id>`: credentials, login, label, notes; `--clear-*` removes one.
  Exclusive use belongs to the persona (`persona exclusive`), not to an account.
- `test-account move <id> --persona <persona>`: the account now signs in for the other
  persona; scenarios keep the personas they play.
- `test-account remove <id> --force`: refused for the last account of a persona scenarios
  still play.
- `persona delete <persona> --force`: refused while a scenario plays it or it still has
  test accounts.

Persona names are unique per app, ignoring case. Every command takes a persona ID or name.
