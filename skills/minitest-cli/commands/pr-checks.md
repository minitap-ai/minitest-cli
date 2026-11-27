# PR checks (`minitest pr`)

A **PR check** tests a pull request without access to its code. CI sends the
builds (iOS, Android) and/or the URL of the web app the PR deployed, and the PR's text (description, ticket, optional images); Mini reads the
app's suite, knowledge and open issues, plans checks in two groups (`change`:
what the PR changes, `impact`: what it could break), verifies them on the
devices, and gives a verdict. The CI job ends there. Mini then proposes suite
changes in the background, applied when you report the PR merged.

One PR = one check (one session in the Test editor). Each `pr check` on the same
PR number adds a **push** to it: the previous push is cancelled if it is still
running, and push N re-tests what failed or needed an answer, what the new
commits touch, and new criteria; the rest is carried over (`--full` re-runs
everything).

## Setup

`minitest pr` talks to Conductor (`MINITEST_CONDUCTOR_URL`, production by
default; dev is `https://conductor.dev.minitap.ai`). Authenticate with a customer
`MINITEST_API_KEY` (`mtk_…`) in CI, or `minitest auth login` locally. Every
command needs the app: `--app ID` or `MINITEST_APP_ID`.

## Exit codes

`minitest pr` has its own exit codes, so a CI step can branch on them:

| Code | Meaning |
| ---- | ------- |
| 0 | `ready`, or `ready_with_warnings` (unless `--fail-on warning`) |
| 1 | `not_ready`: a check is critical (or `ready_with_warnings` with `--fail-on warning`) |
| 2 | `needs_answer`: Mini asked a question. Clarify it in the PR text and run `pr check` again (the next push re-tests every check that asked), or answer it in the session |
| 3 | Anything else: errored on our side, invalid input or flags, rejected key, network, `--timeout` reached, or the push was replaced by a newer one |

`known` (matches an open issue) and `not_tested` results never fail a check.
`--timeout` and a replaced push only stop the waiting: the check keeps running.

## Start a check

```bash
minitest-cli --app "$APP" pr check \
  --pr 1482 --title "Favourites on restaurant cards" \
  --context-file pr.md \
  --ios-build build/App.ipa --android-build build/app.aab \
  [--web-url https://preview.example.com/pr-1482 [--web-browser chrome|firefox|edge] [--web-persona NAME|ID]] \
  [--commits-file commits.txt] [--sha "$SHA"] [--ticket TIM-123] \
  [--attach 'design/*.png' --attach spec.pdf] \
  [--full] [--report-file pr-check.md] [--fail-on warning] \
  [--no-wait] [--timeout 1800]
```

- `--ios-build` / `--android-build` take a build file (uploaded first, an
  `.aab` is converted) or the id of an uploaded build. `--web-url` is the
  http(s) URL of the PR's web build (a preview deployment), checked in
  `--web-browser` (Chrome by default). At least one of the three is required; a
  platform you don't pass is simply not checked. `--web-persona` (a persona id
  or name, see `minitest persona list`) is who Mini signs in as on the web; its
  test accounts and secrets come from the app, as for any web run.
- `--context-file` is Markdown with the PR description and the ticket, at most
  10,000 characters (`-` reads stdin). A longer file exits 3 without sending
  anything: shorten it yourself and keep the acceptance criteria.
- `--commits-file`: the push's commit messages, one per line
  (`git log --format=%s base..head`). Mini re-tests the areas they name.
- `--ticket`: the key of the ticket the PR implements, shown on the report.
- `--attach` (repeatable glob): png, jpg, gif, webp or pdf of at most 10 MB.
  Other files are skipped with a warning; the check goes on.
- `--no-wait`: start, print the check id and report link, exit 0. Follow it
  later with `pr wait`.

## What it prints

The report link comes first, then one line per step: the plan (each check with
its group), each result (`[ios] passed …  @ 1:12`, `[web] …`: the moment in
that platform's recording), Mini's questions, and the verdict with the link again.
A heartbeat line appears at least every 60 s. No colours outside a terminal.

The CLI follows the check's event stream and resumes it after a disconnect
(Last-Event-ID) without printing a line twice; while the stream is down it reads
the report every 15 s.

On GitHub Actions (`GITHUB_ACTIONS=true`) it also groups the log per phase
(`Prepare`, `Explore & verify`), prints one `::error::` annotation per critical
check and platform, and appends the Markdown report to `$GITHUB_STEP_SUMMARY`.

With `--json`, stdout is NDJSON, one object per line: `pr_check.created` (the
check, its push and `reportUrl`), then the events (`pr_check.state`,
`pr_check.plan`, `pr_check.item`, `pr_check.question`, `pr_check.verdict`), and
last `pr_check.result` with `verdict`, `exitCode`, `reportUrl` and the full
`report`.

## Follow up

```bash
minitest-cli --app "$APP" pr wait 1482 [--report-file pr-check.md] [--fail-on warning] [--timeout N]
minitest-cli --app "$APP" pr report 1482 [--push 1]   # Markdown; --json for the report object
minitest-cli --app "$APP" pr merged 1482   # apply Mini's suite edits and new scenarios
minitest-cli --app "$APP" pr closed 1482   # discard them; the suite is unchanged
```

`pr wait` follows the PR's latest push and exits like `pr check`. `pr merged`
applies the proven edits and new scenarios at once and drops unproven ones;
proposed deletions wait for a person to approve them in the webapp. Both answer
409 (exit 3) once the PR is already merged or closed.

## GitHub Actions

```yaml
on: pull_request
jobs:
  pr-check:
    runs-on: ubuntu-latest
    env:
      MINITEST_API_KEY: ${{ secrets.MINITEST_API_KEY }}
      MINITEST_APP_ID: ${{ vars.MINITEST_APP_ID }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: uv tool install minitest-cli
      # … build App.ipa and app.aab …
      - run: |
          printf '# %s\n\n%s\n' "$TITLE" "$BODY" > pr.md
          git log --format=%s origin/${{ github.base_ref }}..HEAD > commits.txt
          minitest-cli pr check --pr ${{ github.event.number }} --title "$TITLE" \
            --context-file pr.md --commits-file commits.txt \
            --sha ${{ github.event.pull_request.head.sha }} \
            --ios-build App.ipa --android-build app.aab
        env:
          TITLE: ${{ github.event.pull_request.title }}
          BODY: ${{ github.event.pull_request.body }}
```

On `pull_request: closed`, run `minitest-cli pr merged <n>` when
`github.event.pull_request.merged` is true, else `minitest-cli pr closed <n>`.
