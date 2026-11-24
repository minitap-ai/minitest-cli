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
platform holding it; a run of another workspace using the same login shows as
`other_workspace`, without ids) or `cooling_down` (until when, and why: `blocked`,
`rate_limited`, `logged_out`, `verification_failed`). An account of a persona without
exclusive use can have several holders (`holderCount`). `persona list` and `persona get`
carry the same counts (`freeCount`, `inUseCount`, `coolingDownCount`, `accountCount`).
`test-account clear-cooldown <id>` puts a cooled account back into rotation.

## Binding scenarios

`scenario-binding set-personas <scenario> --persona A --persona B` replaces the personas a
scenario plays (`--clear` unbinds them all; the scenario then runs as New user).
`list-personas` reads them. Each persona is bound through one of its test accounts (the
one already bound, else its oldest), so a persona needs at least one account first (409
otherwise). Shared Minitap profiles bound to the scenario are left alone.

On a draft feature branch, pass `--draft-feature <df_id>` with the scenario's **main** ID.
In a changeset (`df apply`), `story.create` and `story.edit` ops accept
`"personaIds": ["…"]` instead of `"testProfileIds"` (never both). `df show --view diff`
still reports the accounts the branch binds as `test_profile_ids`.

## Changing accounts

- `test-account update <id>`: credentials, login, label (same flags as
  `test-profile update`).
- `test-account move <id> --persona <persona>`: scenarios bound through the account keep
  their persona through another of its accounts. Moving a persona's last account takes
  its scenarios along and deletes the emptied persona.
- `test-account remove <id> --force`: scenarios move to another account of the persona
  first. Refused for the last account of a persona scenarios still play; removing a
  persona's last account deletes the persona.
- `persona delete <persona> --force`: refused while a scenario plays it or it still has
  test accounts.

Persona names are unique per app, ignoring case. Every command takes a persona ID or name.
