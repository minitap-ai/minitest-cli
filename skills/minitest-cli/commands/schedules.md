# Scheduled runs (`minitest schedules`)

A schedule is a rule on one app: **what runs** (the whole suite, tags minus
excluded scenarios, or picked scenarios), **where** (browsers on a URL or a
branch build; iOS / Android on the latest build, a fixed build, or a branch
build), **when** (a wall-clock time, weekdays, an IANA timezone) and **which
Slack channel** gets the summary. Each start creates an ordinary run, then Mini
posts one Slack message: all clear, what is new since the schedule's previous
run, or why the night did not run.

## When to create one

- The user wants the app checked without anyone pressing Run: "every night",
  "every morning before standup", "watch production between releases".
- The team has no CI wiring, or wants to watch what users have (a fixed build,
  the production URL) rather than each commit. For per-commit checks, use
  `run from-commit` or the CI pattern instead.
- Do not create one to run something once: use `run start` / `run all`.

Ask for, or confirm, the Slack channel ID (Slack: channel details, bottom of
the About tab, `C…`); the summary has nowhere else to go. Each start spends
credits like any run: say how many scenarios run per night (`preview`).

## Create, check, run now

All commands are app-scoped: the global `--json` and `--app` go before
`schedules`. A schedule is addressed by name (case-insensitive) or ID.

```bash
# Weekdays at 03:00 in this machine's timezone, tagged scenarios on desktop + Android Chrome
minitest --json --app $APP schedules create --name "Nightly sanity check" --at 03:00 \
  --tag Navigation --tag Content --exclude "Weather widget shows" \
  --url https://www.example.com --browser chrome --browser chrome:android \
  --slack-channel C0123ABCD --slack-channel-name minitap

# Native: newest build that installs on Android, always the same iOS build, every day in Oslo
minitest --json --app $APP schedules create --name "Monitoring" --at 05:00 \
  --days every-day --timezone Europe/Oslo \
  --android --ios-build <build-id> --slack-channel C0123ABCD

# What tonight would run: scenario count, duration per target, builds it would pick
minitest --json --app $APP schedules preview "Nightly sanity check"

# Start one now through the same path as the nightly start (it posts to Slack too)
minitest --json --app $APP schedules run "Nightly sanity check"
```

`run` returns the fire: `{"status": "started", "batchId": …}` (follow it with
`batch get` / `run verdicts`), or `{"status": "skipped", "skipReason": …}`
when it could not start. A skipped fire is not a CLI error: exit code 0.

## Read what the nights did

```bash
minitest --json --app $APP schedules fires "Nightly sanity check" --limit 5
```

Newest first. Each started fire carries a `summary`: `outcome`
(`passed` / `warning` / `critical` / `errored` / `running`), `passed` /
`total` / `unchecked` checks, `issues[]` with `isNew` (not failing at the
schedule's previous run) — the rest are still open — `fixed[]`
(`{issueId, title}`: failed at the previous run, worked in this one) with
`fixedCount`, and what was tested (`testedBuilds[]`, `testedUrl`, each with
`isNew`). Open the run with its `batchId`. The human table shows New, Still
open and Fixed counts per night.

**A night that didn't run always has a reason**: `status: "skipped"` with
`skipReason` one of `out_of_credits`, `spend_limit`, `subscription_inactive`,
`no_build`, `build_failed`, `previous_still_running`, `no_scenarios`,
`url_unreachable`, `no_phone_free`, and details in `skipDetail`. Report the
reason; never read a missing run as all clear.

## Flags

| Section | Flags |
| --- | --- |
| Name | `--name` |
| When | `--at HH:MM`, `--days weekdays\|weekends\|every-day\|mon,wed,fri` (default weekdays), `--timezone Europe/Oslo` (default: the machine's timezone) |
| What runs | `--suite` (default), `--tag T` (repeatable) with `--exclude <scenario>` (repeatable), or `--scenario <name-or-id>` (repeatable) |
| Web | `--browser BROWSER[:SURFACE]` (`chrome`, `chrome:mobile`, `chrome:tablet`, `chrome:android`, `safari:ios`; default `chrome`), plus `--url URL` or `--web-branch BRANCH` |
| Native | `--ios` / `--android` (latest build that installs), `--ios-build ID` / `--android-build ID` (fixed), `--ios-branch B` / `--android-branch B` (build the branch first), `--<platform>-physical`, `--<platform>-device-type phone\|tablet` |
| Summary | `--slack-channel ID`, `--slack-channel-name NAME`, `--post-all-clear/--no-post-all-clear` (default on) |
| Agents | `--from-file schedule.json\|yaml`: the shape `schedules get --json` prints (read-only fields are ignored); flags override its fields |

`update <schedule>` changes only what you pass: a scope flag replaces what
runs, any `--<platform>-*` flag redefines that platform, `--browser` replaces
the browsers, `--drop web|ios|android` removes one. All branch sources of one
schedule must build the same branch.

## Other commands

```bash
minitest --json --app $APP schedules list
minitest --json --app $APP schedules get "Nightly sanity check"
minitest --json --app $APP schedules pause "Nightly sanity check"     # resume: same shape
minitest --json --app $APP schedules delete "Nightly sanity check" --yes
minitest --json --app $APP schedules restore <schedule-id>            # undo a delete
```

`delete` exits 1 without `--yes`; it never prompts. Past runs of a deleted
schedule stay on the Runs page.

On a workspace or server without scheduled runs, every command exits 4 with
`Scheduled runs are not available on this workspace yet.`
